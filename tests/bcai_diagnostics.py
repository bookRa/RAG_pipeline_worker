#!/usr/bin/env python
"""BCAI Configuration Diagnostic Tool

This script validates BCAI setup by checking:
1. Environment configuration (.env file)
2. Required credentials
3. Network connectivity
4. Authentication
5. API functionality

Run this script to troubleshoot BCAI integration issues.

Usage:
    python tests/bcai_diagnostics.py
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

import requests
from dotenv import load_dotenv


class Colors:
    """Terminal colors for pretty output."""
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    END = '\033[0m'


def print_header(text: str) -> None:
    """Print a section header."""
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*70}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{text}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*70}{Colors.END}\n")


def print_success(text: str) -> None:
    """Print a success message."""
    print(f"{Colors.GREEN}✅ {text}{Colors.END}")


def print_warning(text: str) -> None:
    """Print a warning message."""
    print(f"{Colors.YELLOW}⚠️  {text}{Colors.END}")


def print_error(text: str) -> None:
    """Print an error message."""
    print(f"{Colors.RED}❌ {text}{Colors.END}")


def print_info(text: str) -> None:
    """Print an info message."""
    print(f"{Colors.BLUE}ℹ️  {text}{Colors.END}")


def check_env_file() -> bool:
    """Check if .env file exists and load it."""
    print_header("1. Checking .env File")
    
    env_path = project_root / ".env"
    
    if not env_path.exists():
        print_error(f".env file not found at: {env_path}")
        print_info("Create a .env file based on .env.example")
        return False
    
    print_success(f".env file found at: {env_path}")
    
    # Load the .env file
    load_dotenv(env_path, override=True)
    print_success(".env file loaded successfully")
    
    return True


def check_bcai_config() -> dict[str, str | None]:
    """Check BCAI configuration variables."""
    print_header("2. Checking BCAI Configuration")
    
    config = {
        "provider": os.getenv("LLM__PROVIDER"),
        "model": os.getenv("LLM__MODEL"),
        "api_base": os.getenv("LLM__API_BASE"),
        "api_key": os.getenv("LLM__API_KEY"),
        "conversation_mode": os.getenv("LLM__CONVERSATION_MODE", "non-rag"),
        "conversation_source": os.getenv("LLM__CONVERSATION_SOURCE", "rag-pipeline-worker"),
    }
    
    all_valid = True
    
    # Check provider
    if config["provider"] != "bcai":
        print_error(f"LLM__PROVIDER is '{config['provider']}' but should be 'bcai'")
        print_info("Update your .env file: LLM__PROVIDER=bcai")
        all_valid = False
    else:
        print_success(f"LLM__PROVIDER = bcai")
    
    # Check model
    if not config["model"]:
        print_error("LLM__MODEL is not set")
        print_info("Set in .env: LLM__MODEL=gpt-4o-mini")
        all_valid = False
    elif "sovereign" in config["model"] and "soveregin" in config["model"]:
        print_warning(f"LLM__MODEL has typo: '{config['model']}' (should be 'sovereign')")
        all_valid = False
    else:
        print_success(f"LLM__MODEL = {config['model']}")
    
    # Check API base URL
    if not config["api_base"]:
        print_error("LLM__API_BASE is not set")
        print_info("Set in .env: LLM__API_BASE=https://bcai.web.boeing.com")
        print_info("  or for test: LLM__API_BASE=https://bcai-test.web.boeing.com")
        all_valid = False
    else:
        api_base = config["api_base"]
        if api_base.endswith("/"):
            print_warning(f"LLM__API_BASE should not end with '/': {api_base}")
            config["api_base"] = api_base.rstrip("/")
        
        if "bcai-test" in api_base:
            print_success(f"LLM__API_BASE = {config['api_base']} (TEST environment)")
        elif "bcai" in api_base:
            print_success(f"LLM__API_BASE = {config['api_base']} (PRODUCTION environment)")
        else:
            print_warning(f"LLM__API_BASE doesn't look like BCAI URL: {api_base}")
    
    # Check API key
    if not config["api_key"]:
        print_error("LLM__API_KEY is not set")
        print_info("Set in .env: LLM__API_KEY=<your-bcai-pat-token>")
        all_valid = False
    elif config["api_key"] in ("your-bcai-pat", "your-bcai-pat-token"):
        print_error("LLM__API_KEY is still the placeholder value")
        print_info("Replace with your actual BCAI PAT token")
        all_valid = False
    elif config["api_key"].startswith("sk-"):
        print_warning("LLM__API_KEY looks like an OpenAI key (starts with 'sk-')")
        print_info("BCAI uses UDAL PAT tokens, not OpenAI keys")
        all_valid = False
    else:
        # Mask the key for security
        masked_key = config["api_key"][:8] + "..." + config["api_key"][-4:] if len(config["api_key"]) > 12 else "***"
        print_success(f"LLM__API_KEY = {masked_key}")
    
    # Check optional settings
    print_success(f"LLM__CONVERSATION_MODE = {config['conversation_mode']}")
    print_success(f"LLM__CONVERSATION_SOURCE = {config['conversation_source']}")
    
    if all_valid:
        print_success("All required BCAI configuration variables are set")
    
    return config if all_valid else {}


def check_network_connectivity(api_base: str) -> bool:
    """Check basic network connectivity to BCAI."""
    print_header("3. Checking Network Connectivity")
    
    try:
        # Try to reach the base URL (not an API endpoint, just network check)
        from urllib.parse import urlparse
        parsed = urlparse(api_base)
        host = parsed.netloc or parsed.path
        
        print_info(f"Testing connection to: {host}")
        
        # Simple connection test
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        result = sock.connect_ex((host, 443))  # HTTPS port
        sock.close()
        
        if result == 0:
            print_success(f"Network connection to {host} is working")
            return True
        else:
            print_error(f"Cannot connect to {host} (port 443)")
            print_info("Check if you're on Boeing network or VPN")
            print_info("Verify firewall rules allow outbound HTTPS")
            return False
            
    except Exception as e:
        print_error(f"Network connectivity test failed: {e}")
        print_info("Ensure you're connected to Boeing network or VPN")
        return False


def check_authentication(api_base: str, api_key: str) -> bool:
    """Test BCAI authentication."""
    print_header("4. Checking BCAI Authentication")
    
    headers = {
        "Authorization": f"basic {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    
    payload = {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": "test"}],
        "stream": False,
        "skip_db_save": True,
        "conversation_mode": ["non-rag"],
        "conversation_guid": str(uuid.uuid4()),  # Required by BCAI
    }
    
    url = f"{api_base}/bcai-public-api/conversation"
    print_info(f"Testing authentication at: {url}")
    
    try:
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=30,
        )
        
        print_info(f"Response status: {response.status_code}")
        
        if response.status_code == 200:
            print_success("Authentication successful!")
            data = response.json()
            
            # Show some response details
            if "choices" in data and data["choices"]:
                print_success("Received valid response from BCAI")
                if "usage" in data:
                    usage = data["usage"]
                    print_info(f"Token usage - prompt: {usage.get('prompt_tokens')}, "
                              f"completion: {usage.get('completion_tokens')}")
            return True
            
        elif response.status_code == 401:
            print_error("Authentication failed (401 Unauthorized)")
            print_info("Your API key is invalid or expired")
            print_info("Generate a new BCAI PAT token")
            return False
            
        elif response.status_code == 403:
            print_error("Access forbidden (403 Forbidden)")
            print_info("Your API key doesn't have permission to access BCAI API")
            print_info("Possible causes:")
            print_info("  - API key lacks required permissions")
            print_info("  - Your account doesn't have BCAI access")
            print_info("  - IP address not whitelisted")
            print_info("Contact BCAI support to verify your access")
            return False
            
        elif response.status_code == 404:
            print_error("Endpoint not found (404)")
            print_info("Check your LLM__API_BASE URL is correct")
            print_info(f"Current URL: {api_base}")
            return False
            
        elif response.status_code == 429:
            print_error("Rate limit exceeded (429)")
            print_info("Wait a moment and try again")
            return False
            
        else:
            print_error(f"Unexpected response: {response.status_code}")
            print_info(f"Response: {response.text[:200]}")
            return False
            
    except requests.exceptions.ConnectionError as e:
        print_error(f"Connection error: {e}")
        print_info("Cannot connect to BCAI. Check network/VPN connection")
        return False
        
    except requests.exceptions.Timeout:
        print_error("Request timed out after 30 seconds")
        print_info("BCAI may be slow or unreachable")
        return False
        
    except Exception as e:
        print_error(f"Authentication test failed: {type(e).__name__}: {e}")
        return False


def test_embedding_endpoint(api_base: str, api_key: str) -> bool:
    """Test BCAI embedding endpoint."""
    print_header("5. Checking BCAI Embedding API (Optional)")
    
    # Check if embeddings are configured for BCAI
    embeddings_provider = os.getenv("EMBEDDINGS__PROVIDER")
    if embeddings_provider != "bcai":
        print_info(f"Embeddings provider is '{embeddings_provider}', not 'bcai'")
        print_info("Skipping embedding test")
        return True
    
    headers = {
        "Authorization": f"basic {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    
    payload = {
        "input": "test embedding",
        "model": os.getenv("EMBEDDINGS__MODEL", "text-embedding-3-small"),
    }
    
    url = f"{api_base}/bcai-public-api/embedding"
    print_info(f"Testing embedding endpoint: {url}")
    
    try:
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=30,
        )
        
        if response.status_code == 200:
            print_success("Embedding API is working!")
            data = response.json()
            if "data" in data and data["data"]:
                embedding = data["data"][0].get("embedding", [])
                print_info(f"Generated embedding with {len(embedding)} dimensions")
            return True
        else:
            print_warning(f"Embedding endpoint returned {response.status_code}")
            print_info("You can still use BCAI for LLM, just not embeddings")
            return True  # Not critical
            
    except Exception as e:
        print_warning(f"Embedding test failed: {e}")
        print_info("You can still use BCAI for LLM")
        return True  # Not critical


def check_config_consistency() -> bool:
    """Check for common configuration issues."""
    print_header("6. Checking Configuration Consistency")
    
    issues_found = False
    
    # Check for duplicate provider settings
    provider = os.getenv("LLM__PROVIDER")
    openai_key = os.getenv("OPENAI_API_KEY")
    
    if provider == "bcai" and openai_key and not openai_key.startswith("your-"):
        print_warning("Both BCAI and OpenAI credentials are set")
        print_info("This is OK if intentional, but make sure LLM__PROVIDER=bcai")
    
    # Check model compatibility
    model = os.getenv("LLM__MODEL", "")
    if "sovereign" in model and provider == "bcai":
        print_info(f"Using US-sovereign model: {model}")
    
    # Check for common typos
    api_base = os.getenv("LLM__API_BASE", "")
    if "bcai" not in api_base.lower() and provider == "bcai":
        print_error(f"API_BASE doesn't contain 'bcai': {api_base}")
        issues_found = True
    
    if not issues_found:
        print_success("No configuration inconsistencies detected")
    
    return not issues_found


def print_summary(results: dict[str, bool]) -> None:
    """Print a summary of all checks."""
    print_header("Summary")
    
    total = len(results)
    passed = sum(results.values())
    
    for check, result in results.items():
        if result:
            print_success(check)
        else:
            print_error(check)
    
    print(f"\n{Colors.BOLD}Results: {passed}/{total} checks passed{Colors.END}\n")
    
    if passed == total:
        print_success("✨ All checks passed! BCAI is properly configured.")
        print_info("You can now use BCAI in your pipeline")
    else:
        print_error("⚠️  Some checks failed. Review the errors above.")
        print_info("Fix the issues and run this diagnostic again")


def main() -> int:
    """Run all diagnostic checks."""
    print(f"\n{Colors.BOLD}{Colors.BLUE}BCAI Configuration Diagnostic Tool{Colors.END}")
    print(f"{Colors.BOLD}Project: {project_root}{Colors.END}\n")
    
    results = {}
    
    # 1. Check .env file
    if not check_env_file():
        print_error("\n❌ Cannot proceed without .env file")
        return 1
    
    results["Environment file exists"] = True
    
    # 2. Check BCAI configuration
    config = check_bcai_config()
    results["BCAI configuration valid"] = bool(config)
    
    if not config:
        print_error("\n❌ Cannot proceed with invalid configuration")
        print_info("Fix the configuration errors above and try again")
        return 1
    
    # 3. Check network connectivity
    results["Network connectivity"] = check_network_connectivity(config["api_base"])
    
    if not results["Network connectivity"]:
        print_warning("\n⚠️  Network issues detected. Remaining tests may fail.")
        print_info("Connect to Boeing network/VPN and try again")
    
    # 4. Check authentication
    results["BCAI authentication"] = check_authentication(
        config["api_base"],
        config["api_key"]
    )
    
    # 5. Test embedding endpoint (optional)
    results["BCAI embeddings"] = test_embedding_endpoint(
        config["api_base"],
        config["api_key"]
    )
    
    # 6. Check configuration consistency
    results["Configuration consistency"] = check_config_consistency()
    
    # Print summary
    print_summary(results)
    
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print(f"\n\n{Colors.YELLOW}Diagnostic cancelled by user{Colors.END}\n")
        sys.exit(130)
    except Exception as e:
        print(f"\n{Colors.RED}Unexpected error: {e}{Colors.END}\n")
        import traceback
        traceback.print_exc()
        sys.exit(1)

