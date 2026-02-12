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

func (h *WebhookHandler) Handle(w http.ResponseWriter, r *http.Request) {
	ctx, cancel := context.WithTimeout(r.Context(), 10*time.Second)
	defer cancel()

	datasourceName := r.PathValue("datasource")
	if datasourceName == "" {
		http.Error(w, "datasource name is required", http.StatusBadRequest)
		return
	}

	log.Printf("Webhook received: datasource=%s", datasourceName)

	// 1. Look up the platform from the rule (like ArgoCD looks up settings per-provider).
	platform, platformName, err := h.bundleService.GetPlatformForDatasource(ctx, datasourceName)
	if err != nil {
		log.Printf("Failed to get platform for datasource %s: %v", datasourceName, err)
		http.Error(w, fmt.Sprintf("no configuration found for datasource %q", datasourceName), http.StatusNotFound)
		return
	}

	// 2. Verify the request actually originated from the expected SCM platform.
	//    ArgoCD does this via a header-based switch (X-GitHub-Event, X-Gitlab-Event, etc.).
	//    We do the same dynamically using the platform driver's EventTypeHeader().
	eventTypeHeader := platform.EventTypeHeader()
	eventType := r.Header.Get(eventTypeHeader)
	if eventType == "" {
		log.Printf("Platform mismatch for datasource=%s: expected header %q not present in request", datasourceName, eventTypeHeader)
		http.Error(w, fmt.Sprintf("webhook source mismatch: expected platform %q (header %q missing)", platformName, eventTypeHeader), http.StatusBadRequest)
		return
	}

	// 3. Read the body once — needed for both signature verification and forwarding.
	body, err := io.ReadAll(r.Body)
	if err != nil {
		log.Printf("Failed to read request body: %v", err)
		http.Error(w, "Failed to read request body", http.StatusInternalServerError)
		return
	}

	// 4. Verify webhook signature (like ArgoCD verifies HMAC/token per provider).
	//    ArgoCD checks ErrHMACVerificationFailed per provider; we use the platform's
	//    configured signature header and secret.
	secret := platform.GetSecret()
	if secret != "" {
		signatureHeader := r.Header.Get(platform.GetGitScmSignature())
		if !platform.VerifyWebhook(body, signatureHeader) {
			log.Printf("Invalid webhook signature for datasource=%s platform=%s", datasourceName, platformName)
			http.Error(w, "Invalid signature", http.StatusUnauthorized)
			return
		}
	}

	// 5. Optionally validate the event type is one we care about (push, PR, etc.)
	if !platform.IsPushEvent(eventType) && !platform.IsPREvent(eventType) {
		log.Printf("Ignoring unhandled event type %q for datasource=%s", eventType, datasourceName)
		w.WriteHeader(http.StatusOK)
		io.WriteString(w, `{"message":"event ignored"}`)
		return
	}

	// 6. Forward to orchestrator.
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

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusAccepted)
	io.WriteString(w, `{"task_id":"`+resp.GetTaskId()+`","message":"`+resp.GetMessage()+`"}`)
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

