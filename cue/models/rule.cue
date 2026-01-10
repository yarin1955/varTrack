package models

import "strings"

// Logic for matching files to environments and keys
#Rule: {
	platform:     string
	datasource:   string
	fileName?:    string
	filePathMap?: {[string]: string}

	// Validator 1: Ensure fileName or filePathMap exists
	_pathCheck: true & (fileName != _|_ || filePathMap != _|_)

	repositories: [...string]
	excludeRepositories?: [...string]

	uniqueKeyName: string | *"{repoName}-{env}"
	variablesMap?: {[string]: string}

	syncMode: "git_upsert_all" | "git_smart_repair" | "live_state" | "auto" | *"auto"

	envAsBranch: bool | *false
	envAsPR:     bool | *false
	envAsTags:   bool | *false
	branchMap?: {[string]: string}

	// Validator 4: Template logic for {env}
	_envProvided: (envAsBranch || envAsPR || envAsTags || branchMap != _|_ || filePathMap != _|_)
	if strings.Contains(uniqueKeyName, "{env}") {
		_envCheck: true & _envProvided
	}

	// Pruning and Safety
	prune:          bool | *false
	pruneLast:      bool | *false
	dryRunPrune:    bool | *false
	selfHeal:       bool | *true
	applyStrategy:  "client_side" | "server_side" | *"client_side"
}