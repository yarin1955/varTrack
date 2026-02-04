package business_logic

import (
	"fmt"
	"gateway-service/internal/models"
	"gateway-service/internal/utils"
	"regexp"
)

// ResolveRuleRepositories coordinates the Rule and the Platform
func ResolveRuleRepositories(rule *models.Rule, p utils.Platform) ([]string, error) {
	var err error

	repos := rule.GetAllInclusionPatterns()
	excludeRepos := rule.GetAllExclusionPatterns()
	err = p.Auth()
	if err != nil {
		return nil, fmt.Errorf("failed to auth: %w", err)
	}
	repos, err = p.GetRepos(repos)
	if err != nil {
		return nil, fmt.Errorf("failed to fetch repositories: %w", err)
	}

	var excludeRegexes []*regexp.Regexp
	for _, pattern := range excludeRepos {
		re, err := regexp.Compile(pattern)
		if err != nil {
			// Log error or return it; here we skip invalid regexes
			continue
		}
		excludeRegexes = append(excludeRegexes, re)
	}

	// 2. Filter results using the compiled regexes
	finalRepos := make([]string, 0)
	for _, repo := range repos {
		if !isExcluded(repo, excludeRegexes) {
			finalRepos = append(finalRepos, repo)
		}
	}

	return finalRepos, nil
}

// Helper updated to accept pre-compiled Regexp objects
func isExcluded(repo string, regexes []*regexp.Regexp) bool {
	for _, re := range regexes {
		if re.MatchString(repo) {
			return true
		}
	}
	return false
}
