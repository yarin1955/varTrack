package handlers

import (
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	pb "gateway-service/internal/gen/proto/go/vartrack/v1/services"
	"gateway-service/internal/models"
	"io"
	"log"
	"net/http"
	"strings"
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

	platformName := r.PathValue("platform")
	datasourceName := r.PathValue("datasource")

	if platformName == "" {
		http.Error(w, "platform name is required", http.StatusBadRequest)
		return
	}

	log.Printf("Webhook received: platform=%s datasource=%s", platformName, datasourceName)

	// Get platform using the rule to determine which secret manager to use
	platform, err := h.bundleService.GetPlatformForRule(ctx, platformName, datasourceName)
	if err != nil {
		log.Printf("Failed to get platform %s: %v", platformName, err)
		http.Error(w, err.Error(), http.StatusNotFound)
		return
	}

	signatureHeader := r.Header.Get(platform.GetGitScmSignature())
	secret := platform.GetSecret()

	body, err := io.ReadAll(r.Body)
	if err != nil {
		log.Printf("Failed to read request body: %v", err)
		http.Error(w, "Failed to read request body", http.StatusInternalServerError)
		return
	}

	if secret != "" && !verifySignature(body, signatureHeader, secret) {
		log.Printf("Invalid webhook signature for platform=%s", platformName)
		http.Error(w, "Invalid signature", http.StatusUnauthorized)
		return
	}

	headers := make(map[string]string)
	for k, v := range r.Header {
		if len(v) > 0 {
			headers[k] = v[0]
		}
	}

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

func verifySignature(payload []byte, signatureHeader string, secret string) bool {
	if !strings.HasPrefix(signatureHeader, "sha256=") {
		return false
	}

	actualSignature := signatureHeader[7:]

	mac := hmac.New(sha256.New, []byte(secret))
	mac.Write(payload)
	expectedSignature := hex.EncodeToString(mac.Sum(nil))

	return hmac.Equal([]byte(actualSignature), []byte(expectedSignature))
}
