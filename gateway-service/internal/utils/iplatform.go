package utils

type IPlatform interface {
	// EventTypeHeader returns the HTTP header key used by the provider
	// for event types (e.g. 'X-GitHub-Event')
	EventTypeHeader() string

	// GitSCMSignature returns the HTTP header key used for webhook
	// signature verification
	GitSCMSignature() string

	// IsPushEvent checks if the given event type is a push event
	IsPushEvent(eventType string) bool

	// IsPREvent checks if the given event type is a pull request event
	IsPREvent(eventType string) bool

	// ConstructCloneURL generates the git clone URL (HTTPS or SSH)
	// based on settings
	ConstructCloneURL(repo string) string

	CreateWebhook(repoName string, endpoint string) error

	Auth() error

	Close()

	GetRepos(patterns []string) ([]string, error)
}
