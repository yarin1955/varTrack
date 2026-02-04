//package handlers
//
//import (
//	"fmt"
//	"gateway-service/internal/business_logic"
//	"gateway-service/internal/config" // Your CUE loader package
//	"net/http"
//)
//
//type WebhookHandler struct {
//	platformFactory *business_logic.PlatformFactory
//	configLoader    *config.Loader // This is your CUE loader
//}
//
//func NewWebhookHandler(pf *business_logic.PlatformFactory, cl *config.Loader) *WebhookHandler {
//	return &WebhookHandler{
//		platformFactory: pf,
//		configLoader:    cl,
//	}
//}
//
//func (h *WebhookHandler) Handle(w http.ResponseWriter, r *http.Request) {
//	ctx := r.Context()
//
//	// 1. Path Params
//	platformName := r.PathValue("platform")
//	datasourceName := r.PathValue("datasource")
//
//	// 2. Load from CUE (Resolving config into the Protobuf struct)
//	// Assuming your configLoader has a method that returns *pb_models.Platform
//	platformConfig, err := h.configLoader.GetPlatformConfig(platformName)
//	if err != nil {
//		http.Error(w, "Platform config not found in CUE", http.StatusNotFound)
//		return
//	}
//
//	// 3. Use Factory to get Driver
//	driver, err := h.platformFactory.GetPlatformDriver(ctx, platformConfig)
//	if err != nil {
//		http.Error(w, fmt.Sprintf("Factory error: %v", err), http.StatusInternalServerError)
//		return
//	}
//	defer driver.Close()
//
//	// 4. Use Driver Interface
//	if err := driver.Auth(); err != nil {
//		http.Error(w, "Auth failed", http.StatusUnauthorized)
//		return
//	}
//
//	fmt.Fprintf(w, "Handled %s for %s", platformName, datasourceName)
//}

package handlers

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"gateway-service/internal/config"
	"net/http"
	"strings"
)

//type WebhookHandler struct {
//	bundle *models.Bundle
//	client pb.OrchestratorClient // Inject the gRPC client
//}
//
//func NewWebhookHandler(bundle *models.Bundle, client pb.OrchestratorClient) *WebhookHandler {
//	return &WebhookHandler{
//		bundle: bundle,
//		client: client,
//	}
//}

// type WebhookHandler struct{}

// func NewWebhookHandler() *WebhookHandler {
// 	return &WebhookHandler{}
// }

// type PlatformHandler struct {
// 	platformService *config.PlatformService
// }

// func NewPlatformHandler(platformService *config.PlatformService) *PlatformHandler {
// 	return &PlatformHandler{
// 		platformService: platformService,
// 	}
// }

type WebhookHandler struct {
    platformService *config.PlatformService
}

func NewWebhookHandler(platformService *config.PlatformService) *WebhookHandler {
    return &WebhookHandler{
        platformService: platformService,
    }
}

func (h *WebhookHandler) Handle(w http.ResponseWriter, r *http.Request) {
	// 1. Get parameters from the URL path
	ctx := r.Context()

	// Get platform name from query parameter or path
	platformName := r.URL.Query().Get("platform")
	if platformName == "" {
		http.Error(w, "platform name is required", http.StatusBadRequest)
		return
	}

	// Get platform instance
	platform, err := h.platformService.GetPlatform(ctx, platformName)
	if err != nil {
		http.Error(w, err.Error(), http.StatusNotFound)
		return
	}

	// Get the signature
	signature := platform.GetGitScmSignature()

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{
		"platform":  platformName,
		"signature": signature,
	})
	//platformName := r.PathValue("platform")
	//datasourceName := r.PathValue("datasource")
	//
	//
	//
	//
	//// 4. Read the body for verification
	//body, err := io.ReadAll(r.Body)
	//if err != nil {
	//	http.Error(w, "Failed to read request body", http.StatusInternalServerError)
	//	return
	//}
	//
	//if !verifySignature(body, secret, gitScmSignature) {
	//	http.Error(w, "Invalid signature", http.StatusUnauthorized)
	//	return
	//}
	//
	//// 3. Prepare headers for the gRPC request
	//headers := make(map[string]string)
	//for k, v := range r.Header {
	//	if len(v) > 0 {
	//		headers[k] = v[0]
	//	}
	//}
	//
	//// 4. Call the Python Orchestrator service via gRPC
	//ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	//defer cancel()
	//
	//resp, err := h.client.ProcessWebhook(ctx, &pb.ProcessWebhookRequest{
	//	Platform:   platformName,
	//	Datasource: datasourceName,
	//	RawPayload: string(body),
	//	Headers:    headers,
	//})
	//
	//if err != nil {
	//	http.Error(w, "Failed to forward to orchestrator", http.StatusInternalServerError)
	//	return
	//}
	//
	//// 5. Respond with the task ID from the backend
	//w.Header().Set("Content-Type", "application/json")
	//w.WriteHeader(http.StatusAccepted)
	//io.WriteString(w, `{"task_id":"`+resp.GetTaskId()+`","message":"`+resp.GetMessage()+`"}`)
}

func verifySignature(payload []byte, signatureHeader string, secret string) bool {
	// 1. The header comes in the format "sha256=..."
	if !strings.HasPrefix(signatureHeader, "sha256=") {
		return false
	}

	// 2. Get the actual hex string (strip the prefix)
	actualSignature := signatureHeader[7:]

	// 3. Compute the HMAC-SHA256 of the body
	mac := hmac.New(sha256.New, []byte(secret))
	mac.Write(payload)
	expectedSignature := hex.EncodeToString(mac.Sum(nil))

	// 4. Constant-time comparison to prevent timing attacks
	return hmac.Equal([]byte(actualSignature), []byte(expectedSignature))
}
