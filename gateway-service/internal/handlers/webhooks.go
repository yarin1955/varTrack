package handlers

import (
	"context"
	"fmt"
	pb "gateway-service/internal/gen/proto/go/vartrack/v1/services"
	"gateway-service/internal/models"
	"io"
	"log"
	"net/http"
	"time"
)

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
	datasourceName := r.PathValue("datasource")
	if datasourceName == "" {
		http.Error(w, "datasource name is required", http.StatusBadRequest)
		return
	}

	log.Printf("Webhook received: datasource=%s", datasourceName)

	ctx, cancel := context.WithTimeout(r.Context(), 10*time.Second)
	defer cancel()

	// Resolve platform from rule.
	platform, platformName, err := h.bundleService.GetPlatformForDatasource(ctx, datasourceName)
	if err != nil {
		log.Printf("Failed to get platform for datasource %s: %v", datasourceName, err)
		http.Error(w, fmt.Sprintf("no configuration found for datasource %q", datasourceName), http.StatusNotFound)
		return
	}

	// Shared verification + event filtering.
	body, eventType, ok := h.verifyWebhook(w, r, platform, platformName)
	if !ok {
		return
	}

	// Datasource webhooks accept both push and PR events.
	if !platform.IsPushEvent(eventType) && !platform.IsPREvent(eventType) {
		log.Printf("Ignoring unhandled event type %q for datasource=%s", eventType, datasourceName)
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
		log.Printf("Failed to forward to orchestrator: %v", err)
		http.Error(w, "Failed to forward to orchestrator", http.StatusBadGateway)
		return
	}

	writeJSON(w, http.StatusAccepted, resp.GetTaskId(), resp.GetMessage())
}

// HandleSchemaRegistry processes schema registry webhooks (POST /webhooks/schema-registry).
func (h *WebhookHandler) HandleSchemaRegistry(w http.ResponseWriter, r *http.Request) {
	schemaRegistry := h.bundleService.GetSchemaRegistry()
	if schemaRegistry == nil {
		log.Printf("Schema registry webhook received but no schema_registry configured in bundle")
		http.Error(w, "schema registry not configured", http.StatusNotFound)
		return
	}

	platformName := schemaRegistry.GetPlatform()
	repo := schemaRegistry.GetRepo()
	branch := schemaRegistry.GetBranch()

	log.Printf("Schema registry webhook received: platform=%s repo=%s branch=%s", platformName, repo, branch)

	ctx, cancel := context.WithTimeout(r.Context(), 10*time.Second)
	defer cancel()

	// Resolve platform from schema_registry config.
	managerName := schemaRegistry.GetSecretManager()
	platform, err := h.bundleService.GetPlatform(ctx, platformName, managerName)
	if err != nil {
		log.Printf("Failed to get platform %s for schema registry: %v", platformName, err)
		http.Error(w, fmt.Sprintf("failed to resolve platform %q", platformName), http.StatusInternalServerError)
		return
	}

	// Shared verification + event filtering.
	body, eventType, ok := h.verifyWebhook(w, r, platform, platformName)
	if !ok {
		return
	}

	// Schema registry only cares about push events.
	if !platform.IsPushEvent(eventType) {
		log.Printf("Schema registry: ignoring non-push event %q", eventType)
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
		log.Printf("Failed to forward schema webhook to orchestrator: %v", err)
		http.Error(w, "failed to forward to orchestrator", http.StatusBadGateway)
		return
	}

	writeJSON(w, http.StatusAccepted, resp.GetTaskId(), resp.GetMessage())
}

// ────────────────────────────────────────────
// Shared helpers
// ────────────────────────────────────────────

// verifyWebhook performs platform header check, body read, and signature
// verification. Returns the body bytes, event type, and true if all checks
// passed. On failure it writes the HTTP error and returns false.
func (h *WebhookHandler) verifyWebhook(
	w http.ResponseWriter,
	r *http.Request,
	platform models.Platform,
	platformName string,
) (body []byte, eventType string, ok bool) {

	// 1. Verify the request originated from the expected platform.
	eventTypeHeader := platform.EventTypeHeader()
	eventType = r.Header.Get(eventTypeHeader)
	if eventType == "" {
		log.Printf("Platform mismatch: expected header %q not present (platform=%s)", eventTypeHeader, platformName)
		http.Error(w, fmt.Sprintf("webhook source mismatch: expected platform %q (header %q missing)", platformName, eventTypeHeader), http.StatusBadRequest)
		return nil, "", false
	}

	// 2. Read the body once — needed for both signature verification and forwarding.
	body, err := io.ReadAll(r.Body)
	if err != nil {
		log.Printf("Failed to read request body: %v", err)
		http.Error(w, "failed to read request body", http.StatusInternalServerError)
		return nil, "", false
	}

	// 3. Verify webhook signature.
	secret := platform.GetSecret()
	if secret != "" {
		signatureHeader := r.Header.Get(platform.GetGitScmSignature())
		if !platform.VerifyWebhook(body, signatureHeader) {
			log.Printf("Invalid webhook signature for platform=%s", platformName)
			http.Error(w, "invalid signature", http.StatusUnauthorized)
			return nil, "", false
		}
	}

	return body, eventType, true
}

func writeJSON(w http.ResponseWriter, status int, taskID, message string) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	io.WriteString(w, `{"task_id":"`+taskID+`","message":"`+message+`"}`)
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
