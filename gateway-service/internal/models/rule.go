package models

import pb "gateway-service/internal/gen/proto/go/vartrack/v1/models"

type Rule struct {
	*pb.Rule
}

func (r *Rule) GetAllInclusionPatterns() []string {
	patterns := append([]string{}, r.GetRepositories()...)
	for _, override := range r.GetOverrides() {
		if override.GetEnable() {
			patterns = append(patterns, override.GetMatchRepositories()...)
		}
	}
	return patterns
}

// GetAllExclusionPatterns returns base exclusions and override exclusions
func (r *Rule) GetAllExclusionPatterns() []string {
	patterns := append([]string{}, r.GetExcludeRepositories()...)
	for _, override := range r.GetOverrides() {
		if override.GetEnable() {
			patterns = append(patterns, override.GetExcludeRepositories()...)
		}
	}
	return patterns
}
