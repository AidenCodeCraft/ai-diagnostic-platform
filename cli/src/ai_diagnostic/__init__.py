"""AI Diagnostic Platform - CLI & SDK

Usage as CLI:
    diag analyze test.log
    diag chat "What caused this kernel panic?"
    diag upload /path/to/logs/*.log

Usage as SDK:
    from ai_diagnostic import DiagnosticClient
    client = DiagnosticClient("http://localhost:8000/api/v1")
    result = client.analyze_log("/path/to/test.log")
    print(result.summary)
"""

__version__ = "1.0.0"
