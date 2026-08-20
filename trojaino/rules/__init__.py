from .agent_files import scan_agent_files
from .ci import scan_ci
from .docker import scan_docker
from .mcp import scan_mcp
from .node_routes import scan_node_routes
from .package_json import scan_package_json
from .python_app import scan_python_app
from .secrets import scan_secrets

RULES = [
    scan_package_json,
    scan_ci,
    scan_secrets,
    scan_docker,
    scan_agent_files,
    scan_mcp,
    scan_node_routes,
    scan_python_app,
]
