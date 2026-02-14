"""
OAuth 2.0 Diagnostics and Troubleshooting Module
Comprehensive error detection, logging, and resolution strategies
"""

import os
import logging
import httpx
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlparse, parse_qs

logger = logging.getLogger("oauth-diagnostics")


@dataclass
class DiagnosticResult:
    """Structured diagnostic result with issue details and solutions."""
    category: str  # "redirect_url", "provider_config", "token_exchange", etc.
    severity: str  # "critical", "warning", "info"
    issue: str
    root_cause: str
    solution: str
    code_reference: Optional[str] = None


class OAuthDiagnostics:
    """
    Comprehensive OAuth diagnostics system.
    Validates configurations, identifies common misconfigurations,
    and provides actionable troubleshooting steps.
    """

    def __init__(self):
        self.issues: List[DiagnosticResult] = []
        self.supabase_url = os.environ.get("SB_URL", "").strip()
        self.supabase_key = os.environ.get("SB_KEY", "").strip()
        self.service_role_key = os.environ.get("SB_SERVICE_ROLE_KEY", "").strip()

    # ============================================
    # CONFIGURATION VALIDATION
    # ============================================

    def validate_environment_variables(self) -> List[DiagnosticResult]:
        """Check if all required environment variables are set correctly."""
        issues = []

        if not self.supabase_url:
            issues.append(DiagnosticResult(
                category="environment",
                severity="critical",
                issue="Missing SB_URL environment variable",
                root_cause="SB_URL is not set in environment variables",
                solution="Set SB_URL to your Supabase project URL: https://enqcujmzxtrbfkaungpm.supabase.co",
                code_reference="export SB_URL=https://enqcujmzxtrbfkaungpm.supabase.co"
            ))
        elif not self.supabase_url.startswith("https://"):
            issues.append(DiagnosticResult(
                category="environment",
                severity="critical",
                issue="SB_URL does not use HTTPS",
                root_cause=f"SB_URL is {self.supabase_url} (must be HTTPS)",
                solution="Update SB_URL to use HTTPS: https://enqcujmzxtrbfkaungpm.supabase.co",
                code_reference="SB_URL=https://enqcujmzxtrbfkaungpm.supabase.co"
            ))

        if not self.supabase_key:
            issues.append(DiagnosticResult(
                category="environment",
                severity="critical",
                issue="Missing SB_KEY environment variable",
                root_cause="SB_KEY (anon key) is not set",
                solution="Get your anon key from Supabase Dashboard → Settings → API → anon key",
                code_reference="export SB_KEY=your-anon-key"
            ))

        if not self.service_role_key:
            issues.append(DiagnosticResult(
                category="environment",
                severity="critical",
                issue="Missing SB_SERVICE_ROLE_KEY environment variable",
                root_cause="Service role key is not set",
                solution="Get service role key from Supabase Dashboard → Settings → API → service_role secret",
                code_reference="export SB_SERVICE_ROLE_KEY=your-service-role-key"
            ))

        return issues

    def validate_redirect_urls(self) -> List[DiagnosticResult]:
        """
        Check if redirect URLs are properly configured.
        Most 'no authorization code' errors stem from redirect URL mismatches.
        """
        issues = []

        # Expected redirect URLs for different environments
        expected_urls = [
            "http://localhost:8000/api/auth/callback",
            "https://enqcujmzxtrbfkaungpm.supabase.co/functions/v1/oauth-callback",
            "https://your-domain.com/api/auth/callback",
        ]

        # Common misconfigurations
        common_mistakes = [
            ("http://localhost/api/auth/callback", "localhost without port 8000 - won't match if app runs on :8000"),
            ("https://your-domain.com/auth/callback", "missing /api prefix - should be /api/auth/callback"),
            ("https://enqcujmzxtrbfkaungpm.supabase.co/auth/v1/callback", "supabase auth endpoint - should use functions/v1"),
            ("http://example.com/api/auth/callback", "HTTP instead of HTTPS - OAuth providers require HTTPS"),
            ("/api/auth/callback", "relative URL - must be absolute with domain"),
        ]

        issues.append(DiagnosticResult(
            category="redirect_url",
            severity="info",
            issue="Redirect URL validation checklist",
            root_cause="Most 'no authorization code' errors are redirect URL mismatches",
            solution="Verify these redirect URLs in your OAuth provider settings:\n" +
                    "\n".join([f"  ✓ {url}" for url in expected_urls]) +
                    "\n\nCommon mistakes to avoid:\n" +
                    "\n".join([f"  ✗ {url} - {reason}" for url, reason in common_mistakes]),
            code_reference="Check OAuth provider dashboard under 'Authorized Redirect URIs'"
        ))

        return issues

    # ============================================
    # CALLBACK REQUEST VALIDATION
    # ============================================

    def validate_callback_request(
        self,
        query_params: Dict[str, any],
        request_url: str
    ) -> List[DiagnosticResult]:
        """
        Analyze an incoming callback request to identify issues.
        Called from the /api/auth/callback endpoint.
        """
        issues = []

        # Check 1: Authorization code present
        code = query_params.get("code")
        if not code:
            error = query_params.get("error")
            error_desc = query_params.get("error_description")

            if error:
                issues.append(DiagnosticResult(
                    category="callback",
                    severity="critical",
                    issue=f"OAuth provider returned error: {error}",
                    root_cause=self._interpret_oauth_error(error, error_desc),
                    solution=self._get_oauth_error_solution(error),
                    code_reference=f"error={error}&error_description={error_desc}"
                ))
            else:
                issues.append(DiagnosticResult(
                    category="callback",
                    severity="critical",
                    issue="No authorization code received in callback",
                    root_cause="Possible causes:\n" +
                              "  1. Redirect URL mismatch between app and OAuth provider\n" +
                              "  2. OAuth provider not configured with correct redirect URL\n" +
                              "  3. User canceled the OAuth login\n" +
                              "  4. CSRF token validation failed\n" +
                              "  5. State parameter mismatch",
                    solution="1. Verify redirect URL in OAuth provider settings matches exactly\n" +
                            "2. Check that redirect URL protocol (http/https) matches\n" +
                            "3. Verify redirect URL port number is correct\n" +
                            "4. Check for trailing slashes or query parameters\n" +
                            "5. Restart OAuth flow and check browser network tab",
                    code_reference="GET /api/auth/callback?code=... (code parameter missing)"
                ))

        # Check 2: Request URL validation
        if request_url:
            parsed_url = urlparse(request_url)
            issues.extend(self._validate_request_url(parsed_url))

        # Check 3: State parameter (CSRF protection)
        state = query_params.get("state")
        if state is None:
            issues.append(DiagnosticResult(
                category="security",
                severity="warning",
                issue="State parameter missing from callback",
                root_cause="OAuth provider did not include state parameter for CSRF validation",
                solution="Ensure state parameter validation is properly implemented in your app",
                code_reference="session.get('oauth_state') should match query_params['state']"
            ))

        return issues

    def _validate_request_url(self, parsed_url) -> List[DiagnosticResult]:
        """Validate the request URL for common issues."""
        issues = []

        # Check protocol
        if parsed_url.scheme != "https" and "localhost" not in parsed_url.netloc:
            issues.append(DiagnosticResult(
                category="security",
                severity="warning",
                issue="Non-HTTPS callback URL detected",
                root_cause=f"Callback URL uses {parsed_url.scheme}:// instead of https://",
                solution="Production OAuth callbacks must use HTTPS. Use HTTP only for localhost testing.",
                code_reference=f"Current: {parsed_url.scheme}://{parsed_url.netloc}"
            ))

        # Check for common typos in domain
        if "supabase.co" in parsed_url.netloc:
            if "enqcujmzxtrbfkaungpm" not in parsed_url.netloc:
                issues.append(DiagnosticResult(
                    category="configuration",
                    severity="critical",
                    issue="Incorrect Supabase project ID in callback URL",
                    root_cause="URL contains Supabase domain but wrong project ID",
                    solution="Use your actual project URL: https://enqcujmzxtrbfkaungpm.supabase.co",
                    code_reference=f"Current: {parsed_url.netloc}"
                ))

        return issues

    # ============================================
    # TOKEN EXCHANGE VALIDATION
    # ============================================

    async def validate_token_exchange(self, code: str) -> List[DiagnosticResult]:
        """
        Validate token exchange process with Supabase.
        Identifies issues during the authorization code → token exchange step.
        """
        issues = []

        if not self.supabase_url or not self.supabase_key:
            issues.append(DiagnosticResult(
                category="configuration",
                severity="critical",
                issue="Cannot test token exchange - missing configuration",
                root_cause="SB_URL or SB_KEY not set",
                solution="Set environment variables first (see validate_environment_variables)",
                code_reference="SB_URL={url}, SB_KEY={key}"
            ))
            return issues

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{self.supabase_url}/auth/v1/token?grant_type=authorization_code",
                    headers={
                        "apikey": self.supabase_key,
                        "Content-Type": "application/x-www-form-urlencoded"
                    },
                    data={
                        "code": code,
                        "grant_type": "authorization_code"
                    }
                )

            if response.status_code == 400:
                error_data = response.json()
                error = error_data.get("error")
                error_desc = error_data.get("error_description", "")

                if "invalid_grant" in error:
                    issues.append(DiagnosticResult(
                        category="token_exchange",
                        severity="critical",
                        issue="Invalid authorization code",
                        root_cause="Authorization code is expired, invalid, or already used. Possible causes:\n" +
                                "  1. Code expired (typically 10 minutes)\n" +
                                "  2. Code was already exchanged\n" +
                                "  3. Code doesn't match the client ID\n" +
                                "  4. Redirect URI in code doesn't match request",
                        solution="1. Restart OAuth flow to get a fresh code\n" +
                                "2. Check that you're using the same redirect URI\n" +
                                "3. Verify authorization code is being captured correctly\n" +
                                "4. Check code expiration (typically 10 minutes)",
                        code_reference=f"POST /auth/v1/token returned: {error_desc}"
                    ))
                elif "invalid_client" in error:
                    issues.append(DiagnosticResult(
                        category="token_exchange",
                        severity="critical",
                        issue="Invalid Supabase credentials",
                        root_cause="SB_KEY (anon key) is invalid or doesn't match Supabase project",
                        solution="Get correct anon key from Supabase Dashboard:\n" +
                                "Settings → API → Project API keys → anon (public)",
                        code_reference="Verify SB_KEY matches your project"
                    ))

            elif response.status_code == 401:
                issues.append(DiagnosticResult(
                    category="token_exchange",
                    severity="critical",
                    issue="Unauthorized - API key rejected",
                    root_cause="SB_KEY (anon key) is not authorized for this operation",
                    solution="Ensure SB_KEY is the public anon key, not the service role key",
                    code_reference="SB_KEY should be from Settings → API → anon key"
                ))

            elif response.status_code != 200:
                issues.append(DiagnosticResult(
                    category="token_exchange",
                    severity="critical",
                    issue=f"Token exchange failed with status {response.status_code}",
                    root_cause=f"Supabase returned: {response.text[:200]}",
                    solution="Check Supabase status page and verify all credentials",
                    code_reference=f"Response: {response.text[:200]}"
                ))

        except httpx.TimeoutException:
            issues.append(DiagnosticResult(
                category="network",
                severity="critical",
                issue="Token exchange timeout",
                root_cause="Cannot reach Supabase server (connection timeout after 10s)",
                solution="1. Check internet connection\n" +
                        "2. Verify SB_URL is correct and reachable\n" +
                        "3. Check if Supabase is down (status.supabase.com)\n" +
                        "4. Try increasing timeout value",
                code_reference="httpx.TimeoutException during POST /auth/v1/token"
            ))

        except httpx.RequestError as e:
            issues.append(DiagnosticResult(
                category="network",
                severity="critical",
                issue="Network error during token exchange",
                root_cause=f"HTTP request failed: {str(e)}",
                solution="1. Check network connectivity\n" +
                        "2. Verify SB_URL is valid\n" +
                        "3. Check for firewall/proxy issues",
                code_reference=f"RequestError: {str(e)[:200]}"
            ))

        return issues

    # ============================================
    # ERROR INTERPRETATION
    # ============================================

    def _interpret_oauth_error(self, error: str, error_desc: str) -> str:
        """Interpret OAuth provider error codes."""
        error_meanings = {
            "invalid_request": "OAuth request is missing required parameters or is malformed",
            "invalid_client": "Client authentication failed (invalid client ID or secret)",
            "invalid_grant": "Authorization code is invalid, expired, or already used",
            "unauthorized_client": "Client is not authorized for this OAuth flow",
            "unsupported_grant_type": "Server doesn't support this grant type",
            "invalid_scope": "Requested scope is invalid or not authorized",
            "access_denied": "User denied permission (clicked Cancel)",
            "server_error": "OAuth provider server error",
            "temporarily_unavailable": "OAuth provider temporarily unavailable",
            "redirect_uri_mismatch": "Redirect URI doesn't match registered URI",
        }

        return error_meanings.get(error, error_desc or "Unknown error from OAuth provider")

    def _get_oauth_error_solution(self, error: str) -> str:
        """Get solution for specific OAuth errors."""
        solutions = {
            "invalid_request": "Check that all required OAuth parameters are present and correct",
            "invalid_client": "Verify client ID matches OAuth provider settings",
            "invalid_grant": "Restart OAuth flow to get a fresh authorization code",
            "unauthorized_client": "Enable OAuth flow in provider settings for this client",
            "unsupported_grant_type": "Use 'authorization_code' grant type",
            "invalid_scope": "Verify requested scopes are valid for this OAuth provider",
            "access_denied": "User canceled login. Ask user to try again and grant permission",
            "server_error": "Try again later. Check provider status page if issue persists",
            "temporarily_unavailable": "Wait and retry. Provider may be under maintenance",
            "redirect_uri_mismatch": "Register this redirect URI in OAuth provider settings:\n" +
                                    "  http://localhost:8000/api/auth/callback (development)\n" +
                                    "  https://your-domain.com/api/auth/callback (production)",
        }

        return solutions.get(error, "Check OAuth provider documentation for error details")

    # ============================================
    # COMPREHENSIVE DIAGNOSTICS
    # ============================================

    async def run_full_diagnostics(self) -> Dict:
        """
        Run comprehensive OAuth diagnostics.
        Returns detailed report with all issues and solutions.
        """
        all_issues = []

        # Stage 1: Environment validation
        all_issues.extend(self.validate_environment_variables())

        # Stage 2: Redirect URL validation
        all_issues.extend(self.validate_redirect_urls())

        # Build report
        report = {
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "total_issues": len(all_issues),
                "critical": len([i for i in all_issues if i.severity == "critical"]),
                "warnings": len([i for i in all_issues if i.severity == "warning"]),
                "info": len([i for i in all_issues if i.severity == "info"]),
            },
            "issues_by_category": self._group_issues_by_category(all_issues),
            "all_issues": all_issues,
        }

        return report

    def _group_issues_by_category(self, issues: List[DiagnosticResult]) -> Dict:
        """Group issues by category for better organization."""
        grouped = {}
        for issue in issues:
            if issue.category not in grouped:
                grouped[issue.category] = []
            grouped[issue.category].append(issue)
        return grouped

    def format_report_for_logging(self, report: Dict) -> str:
        """Format diagnostic report as readable log output."""
        summary = report["summary"]
        output = f"""
╔════════════════════════════════════════════════════════════════╗
║              OAuth Diagnostics Report                          ║
╚════════════════════════════════════════════════════════════════╝

Summary:
  Total Issues: {summary['total_issues']}
  Critical: {summary['critical']} ⚠️
  Warnings: {summary['warnings']} ⚠️
  Info: {summary['info']} ℹ️

Issues by Category:
"""
        for category, issues in report["issues_by_category"].items():
            output += f"\n  {category.upper()}:\n"
            for issue in issues:
                severity_icon = "❌" if issue.severity == "critical" else "⚠️" if issue.severity == "warning" else "ℹ️"
                output += f"    {severity_icon} {issue.issue}\n"

        return output
