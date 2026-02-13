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

// maxWebhookBodySize limits the request body to 10 MB. GitHub's maximum
// webhook payload is 25 MB; 10 MB gives comfortable headroom while
// protecting against OOM from oversized payloads.
const maxWebhookBodySize = 10 << 20 // 10 MB

type WebhookHandler struct {
	bundleService *models.Bundle
	client        pb.OrchestratorClient
}

func NewWebhookHandler(bundleService *models.Bundle, client pb.OrchestratorClient) *WebhookHandler {
	return &WebhookHandler{
		bundleService: bundleService,
		client:        client,
	}
}

// Handle processes regular datasource webhooks (POST /webhooks/{datasource}).
func (h *WebhookHandler) Handle(w http.ResponseWriter, r *http.Request) {
	// Content-Type enforcement — inspired by ArgoCD's enforceContentTypes
	// which rejects non-whitelisted Content-Types on mutation requests
	// to mitigate CSRF. Webhooks are always JSON.
	if !isJSONContentType(r) {
		http.Error(w, "Content-Type must be application/json", http.StatusUnsupportedMediaType)
		return
	}

	datasourceName := r.PathValue("datasource")
	if datasourceName == "" {
		http.Error(w, "datasource name is required", http.StatusBadRequest)
		return
	}

	cid := middlewares.GetCorrelationID(r.Context())
	slog.Info("webhook received",
		"datasource", datasourceName,
		"correlation_id", cid,
	)

	ctx, cancel := context.WithTimeout(r.Context(), 10*time.Second)
	defer cancel()
	ctx = injectCorrelationID(ctx, cid)

	// Resolve platform from rule.
	platform, platformName, err := h.bundleService.GetPlatformForDatasource(ctx, datasourceName)
	if err != nil {
		slog.Warn("no platform for datasource",
			"datasource", datasourceName, "error", err, "correlation_id", cid)
		http.Error(w, fmt.Sprintf("no configuration found for datasource %q", datasourceName), http.StatusNotFound)
		return
	}

	// Shared verification + event filtering.
	body, eventType, ok := h.verifyWebhook(w, r, platform, platformName, cid)
	if !ok {
		return
	}

	// Datasource webhooks accept both push and PR events.
	if !platform.IsPushEvent(eventType) && !platform.IsPREvent(eventType) {
		slog.Info("ignoring unhandled event type",
			"event_type", eventType, "datasource", datasourceName, "correlation_id", cid)
		w.WriteHeader(http.StatusOK)
		io.WriteString(w, `{"message":"event ignored"}`)
		return
	}

	// Forward to orchestrator.
	headers := flattenHeaders(r.Header)
	resp, err := h.client.ProcessWebhook(ctx, &pb.ProcessWebhookRequest{
		Platform:   platformName,
		Datasource: datasourceName,
		RawPayload: string(body),
		Headers:    headers,
	})
	if err != nil {
		slog.Error("failed to forward to orchestrator",
			"error", err, "correlation_id", cid)
		http.Error(w, "Failed to forward to orchestrator", http.StatusBadGateway)
		return
	}

	writeJSON(w, http.StatusAccepted, resp.GetTaskId(), resp.GetMessage())
}

// HandleSchemaRegistry processes schema registry webhooks (POST /webhooks/schema-registry).
func (h *WebhookHandler) HandleSchemaRegistry(w http.ResponseWriter, r *http.Request) {
	if !isJSONContentType(r) {
		http.Error(w, "Content-Type must be application/json", http.StatusUnsupportedMediaType)
		return
	}

	schemaRegistry := h.bundleService.GetSchemaRegistry()
	if schemaRegistry == nil {
		slog.Warn("schema registry webhook received but no schema_registry configured in bundle")
		http.Error(w, "schema registry not configured", http.StatusNotFound)
		return
	}

	platformName := schemaRegistry.GetPlatform()
	repo := schemaRegistry.GetRepo()
	branch := schemaRegistry.GetBranch()

	cid := middlewares.GetCorrelationID(r.Context())
	slog.Info("schema registry webhook received",
		"platform", platformName, "repo", repo, "branch", branch, "correlation_id", cid)

	ctx, cancel := context.WithTimeout(r.Context(), 10*time.Second)
	defer cancel()
	ctx = injectCorrelationID(ctx, cid)

	// Resolve platform from schema_registry config.
	managerName := schemaRegistry.GetSecretManager()
	platform, err := h.bundleService.GetPlatform(ctx, platformName, managerName)
	if err != nil {
		slog.Error("failed to get platform for schema registry",
			"platform", platformName, "error", err, "correlation_id", cid)
		http.Error(w, fmt.Sprintf("failed to resolve platform %q", platformName), http.StatusInternalServerError)
		return
	}

	// Shared verification + event filtering.
	body, eventType, ok := h.verifyWebhook(w, r, platform, platformName, cid)
	if !ok {
		return
	}

	// Schema registry only cares about push events.
	if !platform.IsPushEvent(eventType) {
		slog.Info("schema registry: ignoring non-push event",
			"event_type", eventType, "correlation_id", cid)
		w.WriteHeader(http.StatusOK)
		io.WriteString(w, `{"message":"event ignored"}`)
		return
	}

	// Forward to orchestrator via the dedicated schema RPC.
	headers := flattenHeaders(r.Header)
	resp, err := h.client.ProcessSchemaWebhook(ctx, &pb.ProcessSchemaWebhookRequest{
		Platform:   platformName,
		Repo:       repo,
		Branch:     branch,
		RawPayload: string(body),
		Headers:    headers,
	})
	if err != nil {
		slog.Error("failed to forward schema webhook to orchestrator",
			"error", err, "correlation_id", cid)
		http.Error(w, "failed to forward to orchestrator", http.StatusBadGateway)
		return
	}

	writeJSON(w, http.StatusAccepted, resp.GetTaskId(), resp.GetMessage())
}

// ────────────────────────────────────────────
// Shared helpers
// ────────────────────────────────────────────

// verifyWebhook performs platform header check, body read with size cap,
// and signature verification. Returns the body bytes, event type, and
// true if all checks passed. On failure it writes the HTTP error and
// returns false.
func (h *WebhookHandler) verifyWebhook(
	w http.ResponseWriter,
	r *http.Request,
	platform models.Platform,
	platformName string,
	correlationID string,
) (body []byte, eventType string, ok bool) {

	// 1. Verify the request originated from the expected platform.
	eventTypeHeader := platform.EventTypeHeader()
	eventType = r.Header.Get(eventTypeHeader)
	if eventType == "" {
		slog.Warn("platform mismatch: expected event-type header not present",
			"header", eventTypeHeader, "platform", platformName, "correlation_id", correlationID)
		http.Error(w, fmt.Sprintf("webhook source mismatch: expected platform %q (header %q missing)", platformName, eventTypeHeader), http.StatusBadRequest)
		return nil, "", false
	}

	// 2. Read the body with a size cap to prevent OOM from oversized payloads.
	r.Body = http.MaxBytesReader(w, r.Body, maxWebhookBodySize)
	body, err := io.ReadAll(r.Body)
	if err != nil {
		slog.Error("failed to read request body",
			"error", err, "correlation_id", correlationID)
		// MaxBytesReader returns a specific error type on overflow;
		// net/http will have already sent 413 in that case.
		http.Error(w, "failed to read request body", http.StatusRequestEntityTooLarge)
		return nil, "", false
	}

	// 3. Verify webhook signature.
	secret := platform.GetSecret()
	if secret != "" {
		signatureHeader := r.Header.Get(platform.GetGitScmSignature())
		if !platform.VerifyWebhook(body, signatureHeader) {
			slog.Warn("invalid webhook signature",
				"platform", platformName, "correlation_id", correlationID)
			http.Error(w, "invalid signature", http.StatusUnauthorized)
			return nil, "", false
		}
	}

	return body, eventType, true
}

// jsonResponse is the canonical shape for all webhook responses.
type jsonResponse struct {
	TaskID  string `json:"task_id"`
	Message string `json:"message"`
}

// writeJSON encodes the response safely with encoding/json to handle
// special characters correctly (no manual string concatenation).
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

// injectCorrelationID attaches the correlation ID as gRPC outgoing metadata
// so the orchestrator can continue the trace.
func injectCorrelationID(ctx context.Context, id string) context.Context {
	if id == "" {
		return ctx
	}
	return metadata.AppendToOutgoingContext(ctx, middlewares.HeaderCorrelationID, id)
}

// isJSONContentType checks if the request Content-Type is application/json.
// Inspired by ArgoCD's enforceContentTypes which rejects non-whitelisted
// Content-Types on mutation requests to prevent CSRF attacks.
func isJSONContentType(r *http.Request) bool {
	ct := r.Header.Get("Content-Type")
	return strings.HasPrefix(strings.ToLower(strings.TrimSpace(ct)), "application/json")
}
