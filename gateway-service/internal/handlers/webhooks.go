package handlers

import (
	"context"
	"encoding/json"
	"fmt"
	pb "gateway-service/internal/gen/proto/go/vartrack/v1/services"
	"gateway-service/internal/middlewares"
	"gateway-service/internal/models"
	"io"
	"log/slog"
	"net/http"
	"strings"
	"time"

	"google.golang.org/grpc/metadata"
)

// maxWebhookBodySize limits the request body to 10 MB.
//
// ArgoCD's ArgoCDWebhookHandler has a configurable maxWebhookPayloadSizeB
// defaulting to 50 MB. We use a smaller value appropriate for a webhook
// gateway that only needs to forward events.
const maxWebhookBodySize = 10 << 20

type WebhookHandler struct {
	bundleService *models.Bundle
	client        pb.OrchestratorClient

	// breaker protects the gateway from resource exhaustion when the
	// orchestrator is slow or unresponsive.
	//
	// Without a circuit breaker, each request blocks for up to 10s
	// (the gRPC timeout), rapidly consuming goroutines and memory.
	// With it, once consecutive failures exceed the threshold, new
	// requests fail fast with 503.
	//
	// Inspired by:
	//   - ArgoCD's failureRetryRoundTripper (util-kube) which tracks
	//     consecutive failures via shouldRetry() and sleeps between retries.
	//   - ArgoCD's webhook handler queue pattern: when the queue is full,
	//     it immediately returns 503 rather than blocking:
	//       select {
	//       case a.queue <- payload:
	//       default:
	//           http.Error(w, "Queue is full", http.StatusServiceUnavailable)
	//       }
	breaker *middlewares.CircuitBreaker
}

func NewWebhookHandler(
	bundleService *models.Bundle,
	client pb.OrchestratorClient,
	breaker *middlewares.CircuitBreaker,
) *WebhookHandler {
	return &WebhookHandler{
		bundleService: bundleService,
		client:        client,
		breaker:       breaker,
	}
}

// Handle processes regular datasource webhooks (POST /webhooks/{datasource}).
func (h *WebhookHandler) Handle(w http.ResponseWriter, r *http.Request) {
	// Content-Type enforcement — ArgoCD server.go enforceContentTypes():
	//   if allowedTypes[strings.ToLower(r.Header.Get("Content-Type"))] { ... }
	//   else { http.Error(w, "Invalid content type", http.StatusUnsupportedMediaType) }
	if !isJSONContentType(r) {
		writeErrorJSON(w, http.StatusUnsupportedMediaType,
			"Content-Type must be application/json")
		return
	}

	datasourceName := r.PathValue("datasource")
	if datasourceName == "" {
		writeErrorJSON(w, http.StatusBadRequest, "datasource name is required")
		return
	}

	cid := middlewares.GetCorrelationID(r.Context())
	rid := middlewares.GetRequestID(r.Context())
	slog.Info("webhook received",
		"datasource", datasourceName,
		"correlation_id", cid,
		"request_id", rid,
	)

	ctx, cancel := context.WithTimeout(r.Context(), 10*time.Second)
	defer cancel()
	ctx = injectCorrelationID(ctx, cid)

	platform, platformName, err := h.bundleService.GetPlatformForDatasource(ctx, datasourceName)
	if err != nil {
		slog.Warn("no platform for datasource",
			"datasource", datasourceName, "error", err,
			"correlation_id", cid, "request_id", rid)
		writeErrorJSON(w, http.StatusNotFound,
			fmt.Sprintf("no configuration found for datasource %q", datasourceName))
		return
	}

	body, eventType, ok := h.verifyWebhook(w, r, platform, platformName, cid, rid)
	if !ok {
		return
	}

	if !platform.IsPushEvent(eventType) && !platform.IsPREvent(eventType) {
		slog.Info("ignoring unhandled event type",
			"event_type", eventType, "datasource", datasourceName,
			"correlation_id", cid, "request_id", rid)
		writeJSON(w, http.StatusOK, "", "event ignored")
		return
	}

	// 2. Circuit breaker — fail fast when the orchestrator is unresponsive.
	//
	// Mirrors ArgoCD's webhook handler queue-full pattern:
	//   select {
	//   case a.queue <- payload:
	//   default:
	//       http.Error(w, "Queue is full, discarding webhook payload",
	//           http.StatusServiceUnavailable)
	//   }
	// Instead of a queue, we use a state machine that tracks consecutive
	// failures and opens the circuit after MaxFailures.
	if !h.breaker.Allow() {
		slog.Warn("circuit breaker open: failing fast",
			"datasource", datasourceName,
			"correlation_id", cid, "request_id", rid)
		writeErrorJSON(w, http.StatusServiceUnavailable,
			"orchestrator temporarily unavailable, please retry later")
		return
	}

	headers := flattenHeaders(r.Header)
	resp, err := h.client.ProcessWebhook(ctx, &pb.ProcessWebhookRequest{
		Platform: platformName, Datasource: datasourceName,
		RawPayload: string(body), Headers: headers,
	})
	if err != nil {
		h.breaker.RecordFailure()
		slog.Error("failed to forward to orchestrator",
			"error", err, "correlation_id", cid, "request_id", rid)
		writeErrorJSON(w, http.StatusBadGateway,
			"Failed to forward to orchestrator")
		return
	}
	h.breaker.RecordSuccess()
	writeJSON(w, http.StatusAccepted, resp.GetTaskId(), resp.GetMessage())
}

// HandleSchemaRegistry processes schema registry webhooks (POST /webhooks/schema-registry).
func (h *WebhookHandler) HandleSchemaRegistry(w http.ResponseWriter, r *http.Request) {
	if !isJSONContentType(r) {
		writeErrorJSON(w, http.StatusUnsupportedMediaType,
			"Content-Type must be application/json")
		return
	}

	schemaRegistry := h.bundleService.GetSchemaRegistry()
	if schemaRegistry == nil {
		slog.Warn("schema registry webhook received but no schema_registry configured in bundle")
		writeErrorJSON(w, http.StatusNotFound, "schema registry not configured")
		return
	}

	platformName := schemaRegistry.GetPlatform()
	repo := schemaRegistry.GetRepo()
	branch := schemaRegistry.GetBranch()
	cid := middlewares.GetCorrelationID(r.Context())
	rid := middlewares.GetRequestID(r.Context())
	slog.Info("schema registry webhook received",
		"platform", platformName, "repo", repo, "branch", branch,
		"correlation_id", cid, "request_id", rid)

	ctx, cancel := context.WithTimeout(r.Context(), 10*time.Second)
	defer cancel()
	ctx = injectCorrelationID(ctx, cid)

	managerName := schemaRegistry.GetSecretManager()
	platform, err := h.bundleService.GetPlatform(ctx, platformName, managerName)
	if err != nil {
		slog.Error("failed to get platform for schema registry",
			"platform", platformName, "error", err,
			"correlation_id", cid, "request_id", rid)
		writeErrorJSON(w, http.StatusInternalServerError,
			fmt.Sprintf("failed to resolve platform %q", platformName))
		return
	}

	body, eventType, ok := h.verifyWebhook(w, r, platform, platformName, cid, rid)
	if !ok {
		return
	}

	if !platform.IsPushEvent(eventType) {
		slog.Info("schema registry: ignoring non-push event",
			"event_type", eventType,
			"correlation_id", cid, "request_id", rid)
		writeJSON(w, http.StatusOK, "", "event ignored")
		return
	}

	// Circuit breaker check for schema registry too.
	if !h.breaker.Allow() {
		slog.Warn("circuit breaker open: failing fast (schema-registry)",
			"correlation_id", cid, "request_id", rid)
		writeErrorJSON(w, http.StatusServiceUnavailable,
			"orchestrator temporarily unavailable, please retry later")
		return
	}

	headers := flattenHeaders(r.Header)
	resp, err := h.client.ProcessSchemaWebhook(ctx, &pb.ProcessSchemaWebhookRequest{
		Platform: platformName, Repo: repo, Branch: branch,
		RawPayload: string(body), Headers: headers,
	})
	if err != nil {
		h.breaker.RecordFailure()
		slog.Error("failed to forward schema webhook to orchestrator",
			"error", err, "correlation_id", cid, "request_id", rid)
		writeErrorJSON(w, http.StatusBadGateway,
			"failed to forward to orchestrator")
		return
	}
	h.breaker.RecordSuccess()
	writeJSON(w, http.StatusAccepted, resp.GetTaskId(), resp.GetMessage())
}

// ── Shared helpers ──────────────────────────────────────────────────────

// verifyWebhook performs:
//  1. Platform header check
//  2. Size-capped body read (MaxBytesReader)
//  3. Signature verification
//  4. JSON well-formedness validation (json.Valid — O(n), zero alloc)
//  5. Platform-specific structural validation (required fields)
//
// Returns the body, event type, and true if all checks passed.
func (h *WebhookHandler) verifyWebhook(
	w http.ResponseWriter, r *http.Request,
	platform models.Platform, platformName, correlationID, requestID string,
) (body []byte, eventType string, ok bool) {

	// 1. Platform header check.
	eventTypeHeader := platform.EventTypeHeader()
	eventType = r.Header.Get(eventTypeHeader)
	if eventType == "" {
		slog.Warn("platform mismatch: expected event-type header not present",
			"header", eventTypeHeader, "platform", platformName,
			"correlation_id", correlationID, "request_id", requestID)
		writeErrorJSON(w, http.StatusBadRequest,
			fmt.Sprintf("webhook source mismatch: expected platform %q (header %q missing)",
				platformName, eventTypeHeader))
		return nil, "", false
	}

	// 2. Size-capped body read — ArgoCD's webhook handler uses
	// http.MaxBytesReader(w, r.Body, a.maxWebhookPayloadSizeB).
	r.Body = http.MaxBytesReader(w, r.Body, maxWebhookBodySize)
	body, err := io.ReadAll(r.Body)
	if err != nil {
		slog.Error("failed to read request body",
			"error", err, "correlation_id", correlationID, "request_id", requestID)
		writeErrorJSON(w, http.StatusRequestEntityTooLarge,
			"failed to read request body")
		return nil, "", false
	}

	// 3. Signature verification.
	secret := platform.GetSecret()
	if secret != "" {
		signatureHeader := r.Header.Get(platform.GetGitScmSignature())
		if !platform.VerifyWebhook(body, signatureHeader) {
			slog.Warn("invalid webhook signature",
				"platform", platformName,
				"correlation_id", correlationID, "request_id", requestID)
			writeErrorJSON(w, http.StatusUnauthorized, "invalid signature")
			return nil, "", false
		}
	}

	// 4. JSON well-formedness check — rejects truncated/corrupted payloads
	// at the gateway before they consume orchestrator resources. Empty
	// bodies (e.g. GitHub ping events) are allowed through.
	if len(body) > 0 && !json.Valid(body) {
		slog.Warn("webhook payload is not valid JSON",
			"platform", platformName,
			"correlation_id", correlationID, "request_id", requestID,
			"body_len", len(body))
		writeErrorJSON(w, http.StatusBadRequest,
			"request body is not valid JSON")
		return nil, "", false
	}

	// 5. Platform-specific structural validation (improvement #6).
	//
	// Goes beyond json.Valid() to verify the payload has the minimal
	// required fields for the given platform. This prevents junk data
	// from reaching the orchestrator.
	//
	// ArgoCD's webhook handler does implicit validation via the
	// go-playground/webhooks library Parse() method which deserializes
	// into typed structs, rejecting payloads missing required fields.
	// We do a lighter-weight check at the JSON key level.
	if len(body) > 0 {
		if err := validateWebhookStructure(platformName, eventType, body); err != nil {
			slog.Warn("webhook payload failed structural validation",
				"platform", platformName, "event_type", eventType,
				"error", err,
				"correlation_id", correlationID, "request_id", requestID)
			writeErrorJSON(w, http.StatusBadRequest,
				fmt.Sprintf("payload validation failed: %s", err.Error()))
			return nil, "", false
		}
	}

	return body, eventType, true
}

// ── Request body validation (improvement #6) ────────────────────────────

// validateWebhookStructure checks that the JSON payload contains the
// minimal required top-level keys for the given platform and event type.
//
// This is a lightweight alternative to full JSON Schema validation.
// ArgoCD's go-playground/webhooks library validates by deserializing
// into typed Go structs (e.g. github.PushPayload), which implicitly
// rejects payloads missing required fields. We do the same check at
// the key level without deserializing into platform-specific types,
// keeping the gateway platform-agnostic.
//
// ArgoCD's applicationset-webhook (applicationset-webhook/webhook.go)
// similarly switches on event type to determine what fields to extract.
func validateWebhookStructure(platformName, eventType string, body []byte) error {
	// Parse into a generic map — single allocation, no struct coupling.
	var payload map[string]json.RawMessage
	if err := json.Unmarshal(body, &payload); err != nil {
		return fmt.Errorf("failed to parse payload: %w", err)
	}

	var requiredKeys []string

	switch platformName {
	case "github":
		// GitHub push events carry "ref", "repository", "commits".
		// PR events carry "action", "pull_request", "repository".
		// ArgoCD's affectedRevisionInfo switches on the same fields:
		//   case github.PushPayload: payload.Repository.HTMLURL, payload.Ref
		//   case github.PullRequestPayload: payload.Repository.HTMLURL
		switch eventType {
		case "push":
			requiredKeys = []string{"ref", "repository"}
		case "pull_request":
			requiredKeys = []string{"action", "pull_request", "repository"}
		case "ping":
			// Ping events have minimal structure — just "zen" and "hook_id".
			// Allow them through without validation.
			return nil
		default:
			// Unknown event types pass through — the handler will ignore them.
			return nil
		}

	case "gitlab":
		// GitLab push events carry "ref", "project", "commits".
		// ArgoCD's affectedRevisionInfo:
		//   case gitlab.PushEventPayload: payload.Project.WebURL, payload.Ref
		switch eventType {
		case "Push Hook":
			requiredKeys = []string{"ref", "project"}
		case "Tag Push Hook":
			requiredKeys = []string{"ref", "project"}
		case "Merge Request Hook":
			requiredKeys = []string{"object_attributes", "project"}
		default:
			return nil
		}

	case "bitbucket":
		switch eventType {
		case "repo:push":
			requiredKeys = []string{"push", "repository"}
		default:
			return nil
		}

	default:
		// Unknown platform — skip structural validation.
		return nil
	}

	for _, key := range requiredKeys {
		if _, exists := payload[key]; !exists {
			return fmt.Errorf("missing required field %q for %s/%s event",
				key, platformName, eventType)
		}
	}
	return nil
}

type jsonResponse struct {
	TaskID  string `json:"task_id"`
	Message string `json:"message"`
}

func writeJSON(w http.ResponseWriter, status int, taskID, message string) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(jsonResponse{TaskID: taskID, Message: message})
}

func flattenHeaders(h http.Header) map[string]string {
	headers := make(map[string]string, len(h))
	for k, v := range h {
		if len(v) > 0 {
			headers[k] = v[0]
		}
	}
	return headers
}

func injectCorrelationID(ctx context.Context, id string) context.Context {
	if id == "" {
		return ctx
	}
	return metadata.AppendToOutgoingContext(ctx, middlewares.HeaderCorrelationID, id)
}

// isJSONContentType checks if the request Content-Type is application/json.
// Mirrors ArgoCD's enforceContentTypes which rejects non-whitelisted
// Content-Types on mutation requests.
func isJSONContentType(r *http.Request) bool {
	ct := r.Header.Get("Content-Type")
	return strings.HasPrefix(strings.ToLower(strings.TrimSpace(ct)), "application/json")
}
