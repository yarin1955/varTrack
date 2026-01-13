package platforms

import (
	"bytes"
	"context"
	"fmt"
	pb "gateway-service/internal/gen/proto/go/vartrack/v1/models/platforms"
	"net/http"
	"net/url"
	"strings"
)

type GitHub struct {
	*pb.GitHub
}

func (g *GitHub) EventTypeHeader() string {
	return g.GitHub.EventTypeHeader
}

func (g *GitHub) GitSCMSignature() string {
	return g.GitHub.GitScmSignature
}

func (g *GitHub) IsPushEvent(eventType string) bool {
	return eventType == g.GitHub.PushEventName
}

func (g *GitHub) IsPREvent(eventType string) bool {
	return eventType == g.GitHub.PrEventName
}

// ConstructCloneURL derives the git URL from the single endpoint provided
func (g *GitHub) ConstructCloneURL(repo string) string {
	// 1. Normalize Repo (Ensure owner/repo)
	fullRepo := repo
	if !strings.Contains(repo, "/") {
		owner := g.GitHub.GetOrgName()
		if owner == "" {
			owner = g.GitHub.GetUsername()
		}
		if owner != "" {
			fullRepo = fmt.Sprintf("%s/%s", owner, repo)
		}
	}

	u, _ := url.Parse(g.GitHub.Endpoint)
	domain := u.Host

	// 2. Handle SSH
	if g.GitHub.Protocol == "ssh" {
		return fmt.Sprintf("git@%s:%s.git", domain, fullRepo)
	}

	// 3. Handle HTTPS/HTTP
	scheme := u.Scheme
	if scheme == "" {
		scheme = "https"
	}

	auth := ""
	if token := g.GitHub.GetToken(); token != "" {
		auth = fmt.Sprintf("%s@", token)
	} else if user, pass := g.GitHub.GetUsername(), g.GitHub.GetPassword(); user != "" && pass != "" {
		auth = fmt.Sprintf("%s:%s@", user, pass)
	}

	return fmt.Sprintf("%s://%s%s/%s.git", scheme, auth, domain, fullRepo)
}

func (g *GitHub) CreateWebhook(webhookURL string) error {
	// 1. Determine the API base URL
	// For GitHub.com it's api.github.com; for Enterprise it's usually /api/v3
	apiURL := g.GitHub.Endpoint
	if strings.Contains(apiURL, "github.com") && !strings.Contains(apiURL, "api.github.com") {
		apiURL = "https://api.github.com"
	}

	insecureSSL := "0" // Default to verified (secure)
	if !g.GitHub.VerifySsl {
		insecureSSL = "1"
	}
	// 2. Define the payload for GitHub API
	// Note: 'config' contains the URL where GitHub will send the events
	payload := map[string]interface{}{
		"name":   "web",
		"active": true,
		"events": []string{g.GitHub.PushEventName, g.GitHub.PrEventName},
		"config": map[string]interface{}{
			"url":          webhookURL,
			"content_type": "json",
			"secret":       g.GitHub.GetSecret(), // Used for X-Hub-Signature-256
			"insecure_ssl": insecureSSL,
		},
	}

	jsonData, err := json.Marshal(payload)
	if err != nil {
		return fmt.Errorf("failed to marshal webhook payload: %w", err)
	}

	// 3. Construct the Request
	// Note: repo path logic should be handled based on your specific requirements
	// Here we assume a generic path, but you'll likely need to pass the target repo name
	reqURL := fmt.Sprintf("%s/repos/%s/hooks", apiURL, g.GitHub.GetOrgName())

	ctx, cancel := context.WithTimeout(context.Background(), time.Duration(g.GitHub.Timeout)*time.Second)
	defer cancel()

	req, err := http.NewRequestWithContext(ctx, "POST", reqURL, bytes.NewBuffer(jsonData))
	if err != nil {
		return err
	}

	// 4. Set Headers
	req.Header.Set("Accept", "application/vnd.github+json")
	req.Header.Set("Content-Type", "application/json")
	if token := g.GitHub.GetToken(); token != "" {
		req.Header.Set("Authorization", fmt.Sprintf("Bearer %s", token))
	}

	// 5. Execute Request
	client := &http.Client{}
	resp, err := client.Do(req)
	if err != nil {
		return fmt.Errorf("failed to execute webhook creation: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode >= 300 {
		return fmt.Errorf("github api returned error: %s", resp.Status)
	}

	return nil
}
