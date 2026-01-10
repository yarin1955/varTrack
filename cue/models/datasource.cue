package models

import "net"

// Base DataSource settings for external storage systems
#DataSource: {
	name:     string
	endpoint: net.URL
	token?:    string
	username?: string
	password?: string
}