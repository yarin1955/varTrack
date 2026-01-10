package models

import "strings"

// GitHub specific configuration extending the base platform
#GitHubSettings: #Platform & {
	name: "github"

	// Organization Scope
	orgName?: string

	// Connection Reliability
	page_size: int & >=1 & <=100 | *100

	// Property implementations
	event_type_header: "X-Github-Event"
	git_scm_signature: "X-Hub-Signature-256"

	// Derived property: base_api_url logic
	base_api_url: {
		let url = strings.TrimSuffix(endpoint, "/")
		if strings.Contains(url, "github.com") && !strings.Contains(url, "api.github.com") {
			"https://api.github.com"
		}
		if strings.Contains(url, "api/v3") || strings.Contains(url, "api.github.com") {
			url
		}
		"\(url)/api/v3"
	}.out

	// Static method helpers for event identification
	_is_push_event: bool | *(event_type == "push")
	_is_pr_event:   bool | *(event_type == "pull_request")
}