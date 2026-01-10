package models

// The complete system configuration bundle
#Bundle: {
	platforms: [...#Platform]
	datasources: [...#DataSource]
	rules: [...#Rule]
	schema_registry: #SchemaRegistry
}