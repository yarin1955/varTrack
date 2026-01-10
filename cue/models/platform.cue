package models

import "net"

// Base configuration for all Git Providers
#Platform: {
	name:     string
	endpoint: net.URL
	protocol: "ssh" | "http" | "https"

	// Credentials
	token?:    string
	username?: string
	password?: string
	secret?:   string

	// Enterprise / Network settings
	verify_ssl: bool | *true
	timeout:    int & >=1 | *30
	max_retries: int & >=0 | *3

	// Abstract properties and method contracts
	event_type_header: string
	git_scm_signature: string
}