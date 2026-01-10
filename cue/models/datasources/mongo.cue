package models

import "path"

// MongoDB configuration with deep validation
#MongoConfig: #DataSource & {
	host:            string | *"localhost"
	port:            int & >=1 & <=65535 | *27017
	database?:       string
	collection?:     string
	envAsCollection: bool | *false
	update_strategy: "document" | "file"

	// Authentication validation
	if username != _|_ {
		password: string
	}
	if password != _|_ {
		username: string
	}

	// Collection requirement based on strategy
	if !envAsCollection {
		collection: string
	}

	// SSL/TLS and File Path validation
	ssl: bool | *false
	if !ssl {
		ssl_cert_path: _|_
		ssl_key_path:  _|_
		ssl_ca_path:   _|_
	}

	// Capped collection validation
	capped_collection: bool | *false
	if capped_collection {
		capped_size: int & >=1
	}
	if !capped_collection {
		capped_size: _|_
		capped_max:  _|_
	}

	// Connection Pool and Timeouts
	max_pool_size:               int & >=1 | *100
	min_pool_size:               int & >=0 | *0
	connect_timeout_ms:          int & >=0 | *20000
	server_selection_timeout_ms: int & >=0 | *30000
	buffer_size:                 int & >=1 | *1000

	// Enum-like string validations
	read_preference: "primary" | "primaryPreferred" | "secondary" | "secondaryPreferred" | "nearest" | *"primary"
	uuid_representation: "unspecified" | "standard" | "pythonLegacy" | "javaLegacy" | "csharpLegacy" | *"pythonLegacy"
}