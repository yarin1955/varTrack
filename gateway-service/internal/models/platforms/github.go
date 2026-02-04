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

var (
	_ utils.Platform = (*GitHub)(nil)
)

func init() {
	utils.Register("github", newPlatform)
}

type GitHub struct {
	config *pb_gh.GitHub
	client *http.Client
}

func newPlatform() utils.Platform {
	return &GitHub{}
}

func (g *GitHub) Open(ctx context.Context, config *pb_models.Platform) (utils.Platform, error) {
	// 1. Extract the GitHub-specific data from the oneof "envelope"
	ghConfig := config.GetGithub()
	if ghConfig == nil {
		return nil, fmt.Errorf("github driver: configuration is missing or is not a GitHub type")
	}

	// 2. Store the config for use in other methods (Auth, GetRepos, etc.)
	g.config = ghConfig

	// 3. Configure the HTTP Transport
	// We handle SSL verification based on the proto 'verify_ssl' field
	transport := &http.Transport{
		TLSClientConfig: &tls.Config{
			InsecureSkipVerify: !ghConfig.GetVerifySsl(),
		},
	}

	// 4. Initialize the client
	g.client = &http.Client{
		Transport: transport,
		// Convert int32 seconds from proto to time.Duration
		Timeout: time.Duration(ghConfig.GetTimeout()) * time.Second,
	}

	// Return the initialized instance (g) as the IPlatform interface
	return g, nil
}

func (g *GitHub) Close(ctx context.Context) error {
	if g.client != nil {
		if tr, ok := g.client.Transport.(*http.Transport); ok {
			tr.CloseIdleConnections()
		}
	}
	return nil
}

func (g *GitHub) EventTypeHeader() string    { return g.config.EventTypeHeader }
func (g *GitHub) GetGitScmSignature() string { return g.config.GitScmSignature }
func (g *GitHub) IsPushEvent(et string) bool { return et == g.config.PushEventName }
func (g *GitHub) IsPREvent(et string) bool   { return et == g.config.PrEventName }
func (g *GitHub) GetSecret() string          { return g.config.GetSecret() }

func (g *GitHub) Auth(ctx context.Context) error {
	reqURL := fmt.Sprintf("%s/user", g.getBaseAPIURL())
	req, err := http.NewRequestWithContext(ctx, "GET", reqURL, nil)
	if err != nil {
		return err
	}

	g.setAuthHeader(req)
	resp, err := g.client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("github auth failed: %s", resp.Status)
	}
	return nil
}

func (g *GitHub) GetRepos(ctx context.Context, patterns []string) ([]string, error) {
	apiBase := g.getBaseAPIURL()
	var nextURL string
	if org := g.config.GetOrgName(); org != "" {
		nextURL = fmt.Sprintf("%s/orgs/%s/repos?per_page=100", apiBase, org)
	} else {
		nextURL = fmt.Sprintf("%s/user/repos?per_page=100", apiBase)
	}

	resolvedSet := make(map[string]struct{})

	for nextURL != "" {
		req, err := http.NewRequestWithContext(ctx, "GET", nextURL, nil)
		if err != nil {
			return nil, err
		}

		g.setAuthHeader(req)
		req.Header.Set("Accept", "application/vnd.github+json")

		resp, err := g.client.Do(req)
		if err != nil {
			return nil, err
		}

		if resp.StatusCode != http.StatusOK {
			resp.Body.Close()
			return nil, fmt.Errorf("github api error: %s", resp.Status)
		}

		var repos []struct {
			FullName string `json:"full_name"`
		}
		decodeErr := json.NewDecoder(resp.Body).Decode(&repos)
		resp.Body.Close()

		if decodeErr != nil {
			return nil, decodeErr
		}

		for _, repo := range repos {
			for _, pattern := range patterns {
				if matched, _ := path.Match(pattern, repo.FullName); matched {
					resolvedSet[repo.FullName] = struct{}{}
					break
				}
			}
		}
		nextURL = g.getNextPageURL(resp.Header.Get("Link"))
	}

	result := make([]string, 0, len(resolvedSet))
	for repo := range resolvedSet {
		result = append(result, repo)
	}
	return result, nil
}

func (g *GitHub) CreateWebhook(ctx context.Context, repoName, endpoint string) error {
	apiURL := g.getBaseAPIURL()
	targetURL := fmt.Sprintf("%s/%s", strings.TrimSuffix(g.config.Endpoint, "/"), endpoint)

	insecureSSL := "0"
	if !g.config.VerifySsl {
		insecureSSL = "1"
	}

	payload := map[string]interface{}{
		"name":   "web",
		"active": true,
		"events": []string{g.config.PushEventName, g.config.PrEventName},
		"config": map[string]interface{}{
			"url":          targetURL,
			"content_type": "json",
			"secret":       g.config.GetSecret(),
			"insecure_ssl": insecureSSL,
		},
	}

	jsonData, _ := json.Marshal(payload)
	reqURL := fmt.Sprintf("%s/repos/%s/%s/hooks", apiURL, g.config.GetOrgName(), repoName)

	req, err := http.NewRequestWithContext(ctx, "POST", reqURL, bytes.NewBuffer(jsonData))
	if err != nil {
		return err
	}

	g.setAuthHeader(req)
	req.Header.Set("Content-Type", "application/json")

	resp, err := g.client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode >= 300 {
		return fmt.Errorf("github webhook creation failed: %s", resp.Status)
	}
	return nil
}

// Helpers
func (g *GitHub) setAuthHeader(req *http.Request) {
	if token := g.config.GetToken(); token != "" {
		req.Header.Set("Authorization", fmt.Sprintf("Bearer %s", token))
	}
}

func (g *GitHub) getBaseAPIURL() string {
	endpoint := strings.TrimSuffix(g.config.Endpoint, "/")
	if endpoint == "" || strings.Contains(endpoint, "github.com") {
		return "https://api.github.com"
	}
	if !strings.Contains(endpoint, "/api/v3") {
		return endpoint + "/api/v3"
	}
	return endpoint
}

func (g *GitHub) getNextPageURL(linkHeader string) string {
	for _, link := range strings.Split(linkHeader, ",") {
		parts := strings.Split(strings.TrimSpace(link), ";")
		if len(parts) > 1 && strings.TrimSpace(parts[1]) == `rel="next"` {
			return strings.Trim(parts[0], "<>")
		}
	}
	return ""
}

func (g *GitHub) ConstructCloneURL(repo string) string {
	fullRepo := repo
	if !strings.Contains(repo, "/") {
		owner := g.config.GetOrgName()
		if owner == "" {
			owner = g.config.GetUsername()
		}
		fullRepo = fmt.Sprintf("%s/%s", owner, repo)
	}
	u, _ := url.Parse(g.config.Endpoint)
	if g.config.Protocol == "ssh" {
		return fmt.Sprintf("git@%s:%s.git", u.Host, fullRepo)
	}
	auth := ""
	if token := g.config.GetToken(); token != "" {
		auth = fmt.Sprintf("%s@", token)
	}
	return fmt.Sprintf("%s://%s%s/%s.git", u.Scheme, auth, u.Host, fullRepo)
}
