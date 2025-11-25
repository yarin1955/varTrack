from pathlib import Path
from typing import Optional, Dict, Any, List, Literal

from pydantic import Field, field_validator, model_validator, ConfigDict

from app.models.datasource import DataSource
from app.utils.enums.strategy_type import StrategyEnum
from app.utils.factories.datasource_factory import DataSourceFactory


@DataSourceFactory.register()
class MongoConfig(DataSource):
    model_config = ConfigDict(
        extra="forbid",  # ignore unknown fields
        validate_default=True,  # validate defaults
    )
    """
    MongoDB configuration model supporting authentication, SSL/TLS, and advanced options.

    Example JSON:
    {
        "host": "localhost",
        "port": 27017,
        "database": "mydb",
        "collection": "users",
        "username": "admin",
        "password": "secret",
        "ssl": true,
        "ssl_cert_path": "/path/to/cert.pem",
        "ssl_ca_path": "/path/to/ca.pem",
        "auth_source": "admin",
        "replica_set": "rs0"
    }

    Or with envAsCollection:
    {
        "host": "localhost",
        "port": 27017,
        "envAsCollection": true,
        "username": "admin",
        "password": "secret"
    }
    """
    # Basic connection settings
    host: str = Field(default="localhost", description="MongoDB host")
    port: int = Field(default=27017, ge=1, le=65535, description="MongoDB port")
    database: Optional[str] = Field(default=None, description="Database name")
    collection: Optional[str] = Field(default=None, description="Collection name")

    # Runtime collection determination
    envAsCollection: bool = Field(
        default=False,
        description="If true, collection name will be set at runtime (collection field not required)"
    )

    # Multiple hosts for replica sets or sharded clusters
    hosts: Optional[List[str]] = Field(
        default=None,
        description="List of host:port pairs for replica sets (overrides host and port)"
    )

    update_strategy: Literal[StrategyEnum.DOCUMENT, StrategyEnum.FILE] = StrategyEnum.DOCUMENT

    @field_validator('update_strategy', mode='before')
    @classmethod
    def parse_strategy(cls, v):
        if isinstance(v, str):
            enum_val = StrategyEnum(v)
            # Ensure it's only DOCUMENT or FILE
            if enum_val not in (StrategyEnum.DOCUMENT, StrategyEnum.FILE):
                raise ValueError(f"update_strategy must be DOCUMENT or FILE, got {enum_val}")
            return enum_val
        return v

    # Authentication
    username: Optional[str] = Field(default=None, description="Username for authentication")
    password: Optional[str] = Field(default=None, description="Password for authentication")
    auth_source: str = Field(default="admin", description="Authentication database")
    auth_mechanism: Optional[str] = Field(
        default=None,
        description="Authentication mechanism (SCRAM-SHA-1, SCRAM-SHA-256, MONGODB-X509, GSSAPI, PLAIN, MONGODB-AWS)"
    )

    # SSL/TLS settings
    ssl: bool = Field(default=False, description="Enable SSL/TLS")
    ssl_cert_path: Optional[str] = Field(default=None, description="Path to SSL certificate file")
    ssl_key_path: Optional[str] = Field(default=None, description="Path to SSL private key file")
    ssl_ca_path: Optional[str] = Field(default=None, description="Path to SSL CA certificate file")
    ssl_pem_passphrase: Optional[str] = Field(default=None, description="Passphrase for SSL certificate")
    ssl_allow_invalid_certificates: bool = Field(
        default=False,
        description="Allow invalid SSL certificates"
    )
    ssl_allow_invalid_hostnames: bool = Field(
        default=False,
        description="Allow invalid hostnames in SSL certificates"
    )

    # Replica Set configuration
    replica_set: Optional[str] = Field(default=None, description="Replica set name")

    # Connection pool settings
    max_pool_size: int = Field(default=100, ge=1, description="Maximum connection pool size")
    min_pool_size: int = Field(default=0, ge=0, description="Minimum connection pool size")
    max_idle_time_ms: Optional[int] = Field(default=None, ge=0, description="Max idle time in milliseconds")
    connect_timeout_ms: int = Field(default=20000, ge=0, description="Connection timeout in milliseconds")
    socket_timeout_ms: Optional[int] = Field(
        default=None,
        ge=0,
        description="Socket timeout in milliseconds for read/write operations"
    )
    server_selection_timeout_ms: int = Field(
        default=30000,
        ge=0,
        description="Server selection timeout in milliseconds"
    )
    heartbeat_frequency_ms: int = Field(
        default=10000,
        ge=500,
        description="Interval between server monitoring checks in milliseconds"
    )

    # Read operations
    retry_reads: bool = Field(default=True, description="Enable retryable reads")
    read_preference: str = Field(
        default="primary",
        description="Read preference (primary, primaryPreferred, secondary, secondaryPreferred, nearest)"
    )
    max_staleness_seconds: Optional[int] = Field(
        default=None,
        ge=-1,
        description="Maximum replication lag in seconds for secondary reads (-1 to disable)"
    )

    # Read concern
    read_concern_level: Optional[str] = Field(
        default=None,
        description="Read concern level (local, majority, linearizable, snapshot, available)"
    )

    # Write operations
    retry_writes: bool = Field(default=True, description="Enable retryable writes")

    # Write concern
    write_concern_w: Optional[Any] = Field(
        default=None,
        description="Write concern w parameter (number, 'majority', or tag set)"
    )
    write_concern_j: Optional[bool] = Field(
        default=None,
        description="Require acknowledgment that write reached journal"
    )
    write_concern_wtimeout_ms: Optional[int] = Field(
        default=None,
        ge=0,
        description="Time limit for write concern in milliseconds"
    )

    # Compression
    compressors: Optional[List[str]] = Field(
        default=None,
        description="List of compression algorithms to use (snappy, zlib, zstd)"
    )
    zlib_compression_level: int = Field(
        default=-1,
        ge=-1,
        le=9,
        description="Zlib compression level (-1 for default, 0-9)"
    )

    # Direct connection
    direct_connection: bool = Field(
        default=False,
        description="Connect directly to a single host (disables automatic discovery)"
    )

    # Application name
    app_name: Optional[str] = Field(
        default=None,
        max_length=128,
        description="Application name for monitoring and profiling"
    )

    # UUID representation
    uuid_representation: str = Field(
        default="pythonLegacy",
        description="UUID representation format (unspecified, standard, pythonLegacy, javaLegacy, csharpLegacy)"
    )

    # Time zone aware
    tz_aware: bool = Field(
        default=False,
        description="Return timezone-aware datetime objects"
    )

    # Server API
    server_api_version: Optional[str] = Field(
        default=None,
        description="Declare Server API version (e.g., '1')"
    )
    server_api_strict: Optional[bool] = Field(
        default=None,
        description="Enable strict Server API mode"
    )
    server_api_deprecation_errors: Optional[bool] = Field(
        default=None,
        description="Raise errors for deprecated Server API features"
    )

    # Load balancer
    load_balanced: bool = Field(
        default=False,
        description="Use load-balanced mode for MongoDB Atlas or similar services"
    )

    # SRV connection settings
    srv_service_name: str = Field(
        default="mongodb",
        description="Service name for SRV connection strings"
    )
    srv_max_hosts: Optional[int] = Field(
        default=None,
        ge=0,
        description="Maximum number of hosts from SRV records to use"
    )

    # Transaction options
    default_max_commit_time_ms: Optional[int] = Field(
        default=None,
        ge=0,
        description="Default maximum time for transaction commits in milliseconds"
    )

    # Collection validation
    validation_level: Optional[str] = Field(
        default=None,
        description="Document validation level (off, strict, moderate)"
    )
    validation_action: Optional[str] = Field(
        default=None,
        description="Action on validation failure (error, warn)"
    )

    # Collation
    default_collation: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Default collation for string comparisons"
    )

    # Index options
    default_index_commit_quorum: Optional[Any] = Field(
        default=None,
        description="Default commit quorum for index builds (number or 'majority', 'votingMembers')"
    )

    # Capped collection
    capped_collection: bool = Field(
        default=False,
        description="Whether the collection is capped"
    )
    capped_size: Optional[int] = Field(
        default=None,
        ge=1,
        description="Maximum size in bytes for capped collection"
    )
    capped_max: Optional[int] = Field(
        default=None,
        ge=1,
        description="Maximum number of documents in capped collection"
    )

    # Time series collection
    time_series_field: Optional[str] = Field(
        default=None,
        description="Name of the time field for time series collections"
    )
    time_series_meta_field: Optional[str] = Field(
        default=None,
        description="Name of the metadata field for time series collections"
    )
    time_series_granularity: Optional[str] = Field(
        default=None,
        description="Granularity of time series data (seconds, minutes, hours)"
    )

    # Clustered index
    clustered_index: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Clustered index configuration for collection"
    )

    # Change streams
    change_stream_pre_and_post_images: bool = Field(
        default=False,
        description="Enable pre and post images for change streams"
    )

    # Expire after seconds (TTL)
    expire_after_seconds: Optional[int] = Field(
        default=None,
        ge=0,
        description="TTL for documents in seconds"
    )

    # Storage engine
    storage_engine: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Storage engine specific options"
    )

    # Encryption
    auto_encryption_opts: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Client-side field level encryption options"
    )

    # Stable API
    stable_api: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Stable API configuration"
    )

    # Extra options for any additional parameters
    extra_options: Dict[str, Any] = Field(default_factory=dict, description="Additional MongoDB options")

    @field_validator('ssl_cert_path', 'ssl_key_path', 'ssl_ca_path')
    @classmethod
    def validate_file_paths(cls, v: Optional[str]) -> Optional[str]:
        """Validate that SSL certificate paths exist if provided."""
        if v is not None:
            path = Path(v)
            if not path.exists():
                raise ValueError(f"File not found: {v}")
        return v

    @field_validator('read_preference')
    @classmethod
    def validate_read_preference(cls, v: str) -> str:
        """Validate read preference value."""
        valid_prefs = {"primary", "primaryPreferred", "secondary", "secondaryPreferred", "nearest"}
        if v not in valid_prefs:
            raise ValueError(f"Invalid read preference. Must be one of: {valid_prefs}")
        return v

    @field_validator('read_concern_level')
    @classmethod
    def validate_read_concern(cls, v: Optional[str]) -> Optional[str]:
        """Validate read concern level."""
        if v is not None:
            valid_levels = {"local", "majority", "linearizable", "snapshot", "available"}
            if v not in valid_levels:
                raise ValueError(f"Invalid read concern level. Must be one of: {valid_levels}")
        return v

    @field_validator('validation_level')
    @classmethod
    def validate_validation_level(cls, v: Optional[str]) -> Optional[str]:
        """Validate document validation level."""
        if v is not None:
            valid_levels = {"off", "strict", "moderate"}
            if v not in valid_levels:
                raise ValueError(f"Invalid validation level. Must be one of: {valid_levels}")
        return v

    @field_validator('validation_action')
    @classmethod
    def validate_validation_action(cls, v: Optional[str]) -> Optional[str]:
        """Validate validation action."""
        if v is not None:
            valid_actions = {"error", "warn"}
            if v not in valid_actions:
                raise ValueError(f"Invalid validation action. Must be one of: {valid_actions}")
        return v

    @field_validator('time_series_granularity')
    @classmethod
    def validate_time_series_granularity(cls, v: Optional[str]) -> Optional[str]:
        """Validate time series granularity."""
        if v is not None:
            valid_granularities = {"seconds", "minutes", "hours"}
            if v not in valid_granularities:
                raise ValueError(f"Invalid granularity. Must be one of: {valid_granularities}")
        return v

    @field_validator('uuid_representation')
    @classmethod
    def validate_uuid_representation(cls, v: str) -> str:
        """Validate UUID representation."""
        valid_reps = {"unspecified", "standard", "pythonLegacy", "javaLegacy", "csharpLegacy"}
        if v not in valid_reps:
            raise ValueError(f"Invalid UUID representation. Must be one of: {valid_reps}")
        return v

    @model_validator(mode='after')
    def validate_auth_config(self) -> 'MongoConfig':
        """Validate authentication configuration consistency."""
        if self.username and not self.password:
            raise ValueError("Password is required when username is provided")
        if self.password and not self.username:
            raise ValueError("Username is required when password is provided")
        return self

    @model_validator(mode='after')
    def validate_collection_config(self) -> 'MongoConfig':
        """Validate collection configuration - collection is only required if envAsCollection is False."""
        if not self.envAsCollection and not self.collection:
            raise ValueError("collection is required when envAsCollection is False")
        return self

    @model_validator(mode='after')
    def validate_ssl_config(self) -> 'MongoConfig':
        """Validate SSL configuration consistency."""
        if not self.ssl and (self.ssl_cert_path or self.ssl_key_path or self.ssl_ca_path):
            raise ValueError("SSL must be enabled when SSL certificate paths are provided")
        return self

    @model_validator(mode='after')
    def validate_capped_collection(self) -> 'MongoConfig':
        """Validate capped collection configuration."""
        if not self.capped_collection and (self.capped_size or self.capped_max):
            raise ValueError("capped_collection must be True when capped_size or capped_max is specified")
        if self.capped_collection and not self.capped_size:
            raise ValueError("capped_size is required when capped_collection is True")
        return self

    @model_validator(mode='after')
    def validate_time_series(self) -> 'MongoConfig':
        """Validate time series collection configuration."""
        if (self.time_series_meta_field or self.time_series_granularity) and not self.time_series_field:
            raise ValueError("time_series_field is required when using time series options")
        return self

    @model_validator(mode='after')
    def validate_server_api(self) -> 'MongoConfig':
        """Validate Server API configuration."""
        if (
                self.server_api_strict is not None or self.server_api_deprecation_errors is not None) and not self.server_api_version:
            raise ValueError("server_api_version is required when using Server API options")
        return self

    @model_validator(mode='after')
    def validate_connection_mode(self) -> 'MongoConfig':
        """Validate connection mode settings."""
        if self.direct_connection and self.replica_set:
            raise ValueError("Cannot use direct_connection with replica_set")
        if self.load_balanced and (self.direct_connection or self.replica_set):
            raise ValueError("load_balanced cannot be used with direct_connection or replica_set")
        return self

    def get_connection_string(self, runtime_database: Optional[str] = None) -> str:
        """
        Generate MongoDB connection string from configuration.

        Args:
            runtime_database: Optional database name to use at runtime (overrides config database)

        Returns:
            MongoDB connection URI string
        """
        # Build authentication part
        auth = ""
        if self.username and self.password:
            auth = f"{self.username}:{self.password}@"

        # Build host part
        if self.hosts:
            host_part = ",".join(self.hosts)
        else:
            host_part = f"{self.host}:{self.port}"

        # Determine database to use
        db = runtime_database or self.database or ""

        # Build base URI
        if db:
            uri = f"mongodb://{auth}{host_part}/{db}"
        else:
            uri = f"mongodb://{auth}{host_part}"

        # Build query parameters
        params = []

        if self.auth_source and self.username:
            params.append(f"authSource={self.auth_source}")

        if self.auth_mechanism:
            params.append(f"authMechanism={self.auth_mechanism}")

        if self.ssl:
            params.append("ssl=true")
            if self.ssl_cert_path:
                params.append(f"tlsCertificateKeyFile={self.ssl_cert_path}")
            if self.ssl_ca_path:
                params.append(f"tlsCAFile={self.ssl_ca_path}")
            if self.ssl_allow_invalid_certificates:
                params.append("tlsAllowInvalidCertificates=true")
            if self.ssl_allow_invalid_hostnames:
                params.append("tlsAllowInvalidHostnames=true")

        if self.replica_set:
            params.append(f"replicaSet={self.replica_set}")

        params.append(f"maxPoolSize={self.max_pool_size}")
        params.append(f"minPoolSize={self.min_pool_size}")

        if self.max_idle_time_ms:
            params.append(f"maxIdleTimeMS={self.max_idle_time_ms}")

        params.append(f"connectTimeoutMS={self.connect_timeout_ms}")

        if self.socket_timeout_ms:
            params.append(f"socketTimeoutMS={self.socket_timeout_ms}")

        params.append(f"serverSelectionTimeoutMS={self.server_selection_timeout_ms}")
        params.append(f"heartbeatFrequencyMS={self.heartbeat_frequency_ms}")

        params.append(f"retryWrites={str(self.retry_writes).lower()}")
        params.append(f"retryReads={str(self.retry_reads).lower()}")
        params.append(f"readPreference={self.read_preference}")

        if self.max_staleness_seconds is not None and self.max_staleness_seconds >= 0:
            params.append(f"maxStalenessSeconds={self.max_staleness_seconds}")

        if self.write_concern_w is not None:
            params.append(f"w={self.write_concern_w}")

        if self.write_concern_j is not None:
            params.append(f"journal={str(self.write_concern_j).lower()}")

        if self.write_concern_wtimeout_ms:
            params.append(f"wTimeoutMS={self.write_concern_wtimeout_ms}")

        if self.read_concern_level:
            params.append(f"readConcernLevel={self.read_concern_level}")

        if self.compressors:
            params.append("compressors=" + ",".join(self.compressors))
            if "zlib" in self.compressors and self.zlib_compression_level != -1:
                params.append(f"zlibCompressionLevel={self.zlib_compression_level}")

        if self.direct_connection:
            params.append("directConnection=true")

        if self.load_balanced:
            params.append("loadBalanced=true")

        if self.app_name:
            params.append(f"appName={self.app_name}")

        params.append(f"uuidRepresentation={self.uuid_representation}")

        if self.server_api_version:
            params.append(f"serverApi={self.server_api_version}")

        params.append(f"srvServiceName={self.srv_service_name}")

        if self.srv_max_hosts:
            params.append(f"srvMaxHosts={self.srv_max_hosts}")

        # Add extra options
        for key, value in self.extra_options.items():
            params.append(f"{key}={value}")

        if params:
            uri += "?" + "&".join(params)

        return uri

    def get_pymongo_options(self) -> Dict[str, Any]:
        """
        Generate options dictionary for PyMongo MongoClient.

        Returns:
            Dictionary of PyMongo connection options
        """
        options = {
            "maxPoolSize": self.max_pool_size,
            "minPoolSize": self.min_pool_size,
            "connectTimeoutMS": self.connect_timeout_ms,
            "serverSelectionTimeoutMS": self.server_selection_timeout_ms,
            "heartbeatFrequencyMS": self.heartbeat_frequency_ms,
            "retryWrites": self.retry_writes,
            "retryReads": self.retry_reads,
            "tz_aware": self.tz_aware,
            "uuidRepresentation": self.uuid_representation,
        }

        # Host configuration
        if self.hosts:
            options["host"] = self.hosts
        else:
            options["host"] = self.host
            options["port"] = self.port

        if self.username and self.password:
            options["username"] = self.username
            options["password"] = self.password
            options["authSource"] = self.auth_source

        if self.auth_mechanism:
            options["authMechanism"] = self.auth_mechanism

        if self.ssl:
            options["tls"] = True
            if self.ssl_cert_path:
                options["tlsCertificateKeyFile"] = self.ssl_cert_path
            if self.ssl_ca_path:
                options["tlsCAFile"] = self.ssl_ca_path
            if self.ssl_pem_passphrase:
                options["tlsCertificateKeyFilePassword"] = self.ssl_pem_passphrase
            if self.ssl_allow_invalid_certificates:
                options["tlsAllowInvalidCertificates"] = self.ssl_allow_invalid_certificates
            if self.ssl_allow_invalid_hostnames:
                options["tlsAllowInvalidHostnames"] = self.ssl_allow_invalid_hostnames

        if self.replica_set:
            options["replicaSet"] = self.replica_set

        if self.max_idle_time_ms:
            options["maxIdleTimeMS"] = self.max_idle_time_ms

        if self.socket_timeout_ms:
            options["socketTimeoutMS"] = self.socket_timeout_ms

        if self.max_staleness_seconds is not None and self.max_staleness_seconds >= 0:
            options["maxStalenessSeconds"] = self.max_staleness_seconds

        if self.write_concern_w is not None:
            options["w"] = self.write_concern_w

        if self.write_concern_j is not None:
            options["journal"] = self.write_concern_j

        if self.write_concern_wtimeout_ms:
            options["wTimeoutMS"] = self.write_concern_wtimeout_ms

        if self.read_concern_level:
            options["readConcernLevel"] = self.read_concern_level

        if self.compressors:
            options["compressors"] = self.compressors
            if "zlib" in self.compressors and self.zlib_compression_level != -1:
                options["zlibCompressionLevel"] = self.zlib_compression_level

        if self.direct_connection:
            options["directConnection"] = self.direct_connection

        if self.load_balanced:
            options["loadBalanced"] = self.load_balanced

        if self.app_name:
            options["appName"] = self.app_name

        if self.server_api_version:
            from pymongo.server_api import ServerApi
            options["server_api"] = ServerApi(
                self.server_api_version,
                strict=self.server_api_strict,
                deprecation_errors=self.server_api_deprecation_errors
            )

        options["srvServiceName"] = self.srv_service_name

        if self.srv_max_hosts:
            options["srvMaxHosts"] = self.srv_max_hosts

        if self.default_collation:
            options["collation"] = self.default_collation

        if self.auto_encryption_opts:
            options["auto_encryption_opts"] = self.auto_encryption_opts

        # Add extra options
        options.update(self.extra_options)

        return options

    def get_collection_options(self) -> Dict[str, Any]:
        """
        Generate options dictionary for creating a MongoDB collection.

        Returns:
            Dictionary of collection creation options
        """
        options = {}

        if self.capped_collection:
            options["capped"] = True
            options["size"] = self.capped_size
            if self.capped_max:
                options["max"] = self.capped_max

        if self.time_series_field:
            options["timeseries"] = {
                "timeField": self.time_series_field
            }
            if self.time_series_meta_field:
                options["timeseries"]["metaField"] = self.time_series_meta_field
            if self.time_series_granularity:
                options["timeseries"]["granularity"] = self.time_series_granularity

        if self.expire_after_seconds is not None:
            options["expireAfterSeconds"] = self.expire_after_seconds

        if self.clustered_index:
            options["clusteredIndex"] = self.clustered_index

        if self.change_stream_pre_and_post_images:
            options["changeStreamPreAndPostImages"] = {"enabled": True}

        if self.validation_level or self.validation_action:
            validator_opts = {}
            if self.validation_level:
                validator_opts["validationLevel"] = self.validation_level
            if self.validation_action:
                validator_opts["validationAction"] = self.validation_action
            options.update(validator_opts)

        if self.default_collation:
            options["collation"] = self.default_collation

        if self.storage_engine:
            options["storageEngine"] = self.storage_engine

        return options