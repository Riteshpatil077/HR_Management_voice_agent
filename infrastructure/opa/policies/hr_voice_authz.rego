package hr_voice.authz

import future.keywords.if
import future.keywords.in

# =============================================================================
# HR Voice Agent — OPA Authorization Policy (Base)
# Evaluates: allow / deny based on JWT claims and resource paths
# =============================================================================

default allow := false

# ── Allow health check endpoints unconditionally ───────────────────────────────
allow if {
    input.path[0] in {"health", "readiness", "metrics", "openapi.json", "docs"}
}

# ── Allow authenticated users with correct roles ───────────────────────────────
allow if {
    is_authenticated
    has_required_role
}

# ── Super-admin bypass ─────────────────────────────────────────────────────────
allow if {
    input.user.role == "super_admin"
}

# ── Helpers ────────────────────────────────────────────────────────────────────
is_authenticated if {
    input.user.tenant_id != ""
    input.user.sub != ""
}

has_required_role if {
    allowed_roles_for_path[input.path[0]][_] == input.user.role
}

allowed_roles_for_path := {
    "v1": ["hr_admin", "recruiter", "system", "employee", "super_admin"],
}
