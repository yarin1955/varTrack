package platforms

import (
	"bytes"
	"context"
	"crypto/tls"
	"encoding/json"
	"fmt"
	pb_models "gateway-service/internal/gen/proto/go/vartrack/v1/models"
	pb_gh "gateway-service/internal/gen/proto/go/vartrack/v1/models/platforms"
	"gateway-service/internal/utils"
	"net/http"
	"net/url"
	"path"
	"strings"
	"time"
)

type GitHub struct {
	*pb_gh.GitHub
	client *http.Client
}

func init() {
	// Explicitly configuring the registry key for this implementation.
	utils.Register("github", Create)
}

func Create(p *pb_models.Platform) (utils.IPlatform, error) {
	// Logic to initialize the GitHub source
	return &GitHub{GitHub: p.GetGithub()}, nil
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

func (g *GitHub) CreateWebhook(repoName string, endpoint string) error {
	// 1. Determine the API base URL
	apiURL := g.getBaseAPIURL()

	// 2. Construct the Target Webhook URL (The 'Payload URL' in GitHub)
	// This uses your service's endpoint logic: {base_url}/{endpoint}
	targetURL := fmt.Sprintf("%s/%s", strings.TrimSuffix(g.GitHub.Endpoint, "/"), endpoint)

	insecureSSL := "0"
	if !g.GitHub.VerifySsl {
		insecureSSL = "1"
	}

	// 3. Define the payload for GitHub API
	payload := map[string]interface{}{
		"name":   "web",
		"active": true,
		"events": []string{g.GitHub.PushEventName, g.GitHub.PrEventName},
		"config": map[string]interface{}{
			"url":          targetURL,
			"content_type": "json",
			"secret":       g.GitHub.GetSecret(),
			"insecure_ssl": insecureSSL,
		},
	}

	jsonData, err := json.Marshal(payload)
	if err != nil {
		return fmt.Errorf("failed to marshal webhook payload: %w", err)
	}

	// 4. Construct the API Request URL
	// GitHub requires: /repos/{owner}/{repo}/hooks
	reqURL := fmt.Sprintf("%s/repos/%s/%s/hooks", apiURL, g.GitHub.GetOrgName(), repoName)

	ctx, cancel := context.WithTimeout(context.Background(), time.Duration(g.GitHub.Timeout)*time.Second)
	defer cancel()

	req, err := http.NewRequestWithContext(ctx, "POST", reqURL, bytes.NewBuffer(jsonData))
	if err != nil {
		return err
	}

	// 5. Set Headers
	req.Header.Set("Accept", "application/vnd.github+json")
	req.Header.Set("Content-Type", "application/json")
	if token := g.GitHub.GetToken(); token != "" {
		req.Header.Set("Authorization", fmt.Sprintf("Bearer %s", token))
	}

	// 6. Execute Request
	client := &http.Client{}
	resp, err := client.Do(req)
	if err != nil {
		return fmt.Errorf("failed to execute webhook creation: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode >= 300 {
		return fmt.Errorf("github api returned error: %s (status code: %d)", resp.Status, resp.StatusCode)
	}

	return nil
}

func (g *GitHub) Auth() error {
	// 1. Initialize the client with a custom Transport if needed (e.g., for SSL verification)
	tr := &http.Transport{
		TLSClientConfig: &tls.Config{InsecureSkipVerify: !g.GitHub.VerifySsl},
	}

	g.client = &http.Client{
		Transport: tr,
		Timeout:   time.Duration(g.GitHub.Timeout) * time.Second,
	}

	// 2. Verify connection (Lazy Check)
	reqURL := fmt.Sprintf("%s/user", g.getBaseAPIURL())
	req, err := http.NewRequest("GET", reqURL, nil)
	if err != nil {
		return err
	}

	// Set Auth Header
	if token := g.GitHub.GetToken(); token != "" {
		req.Header.Set("Authorization", fmt.Sprintf("Bearer %s", token))
	}

	resp, err := g.client.Do(req)
	if err != nil {
		return fmt.Errorf("github connection failed: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("github auth failed with status: %s", resp.Status)
	}

	return nil
}

func (g *GitHub) Close() {
	if g.client != nil {
		// Close idle connections to "disconnect" from the SCM host
		if tr, ok := g.client.Transport.(*http.Transport); ok {
			tr.CloseIdleConnections()
		}
		g.client = nil
	}
}

func (g *GitHub) GetRepos(patterns []string) ([]string, error) {
	// 1. Internal Context Management
	// Uses the timeout from the GitHub protobuf model
	ctx, cancel := context.WithTimeout(context.Background(), time.Duration(g.GitHub.Timeout)*time.Second)
	defer cancel()

	// 2. Determine API Base (GitHub.com vs Enterprise)
	apiBase := g.getBaseAPIURL()

	var nextURL string
	if org := g.GitHub.GetOrgName(); org != "" {
		nextURL = fmt.Sprintf("%s/orgs/%s/repos?per_page=100", apiBase, org)
	} else {
		nextURL = fmt.Sprintf("%s/user/repos?per_page=100", apiBase)
	}

	resolvedSet := make(map[string]struct{})
	client := &http.Client{}

	// 3. Paginated Fetch & Match
	for nextURL != "" {
		req, err := http.NewRequestWithContext(ctx, "GET", nextURL, nil)
		if err != nil {
			return nil, err
		}

		req.Header.Set("Accept", "application/vnd.github+json")
		if token := g.GitHub.GetToken(); token != "" {
			req.Header.Set("Authorization", fmt.Sprintf("Bearer %s", token))
		}

		resp, err := client.Do(req)
		if err != nil {
			return nil, err
		}
		defer resp.Body.Close()

		if resp.StatusCode != http.StatusOK {
			return nil, fmt.Errorf("github api error: %s", resp.Status)
		}

		var repos []struct {
			FullName string `json:"full_name"` // e.g., "owner/repo"
		}
		if err := json.NewDecoder(resp.Body).Decode(&repos); err != nil {
			return nil, err
		}

		// 4. Pattern Matching against Full Name
		for _, repo := range repos {
			for _, pattern := range patterns {
				// Use path.Match for URL-style slash awareness
				matched, err := path.Match(pattern, repo.FullName)
				if err != nil {
					return nil, fmt.Errorf("invalid pattern %s: %w", pattern, err)
				}
				if matched {
					resolvedSet[repo.FullName] = struct{}{}
					break
				}
			}
		}

		// Parse 'Link' header for next page
		nextURL = g.getNextPageURL(resp.Header.Get("Link"))
	}

	// 5. Build result slice
	result := make([]string, 0, len(resolvedSet))
	for repo := range resolvedSet {
		result = append(result, repo)
	}
	return result, nil
}

// Helper: Extracts the 'next' URL from GitHub's Link header
func (g *GitHub) getNextPageURL(linkHeader string) string {
	if linkHeader == "" {
		return ""
	}
	// Format: <url>; rel="next", <url>; rel="last"
	for _, link := range strings.Split(linkHeader, ",") {
		parts := strings.Split(strings.TrimSpace(link), ";")
		if len(parts) > 1 && strings.TrimSpace(parts[1]) == `rel="next"` {
			return strings.Trim(parts[0], "<>")
		}
	}
	return ""
}

// Helper: Standardizes the API URL for GitHub.com vs Enterprise
func (g *GitHub) getBaseAPIURL() string {
	endpoint := strings.TrimSuffix(g.GitHub.Endpoint, "/")
	if endpoint == "" || strings.Contains(endpoint, "github.com") {
		return "https://api.github.com"
	}
	if !strings.Contains(endpoint, "/api/v3") {
		return endpoint + "/api/v3"
	}
	return endpoint
}
