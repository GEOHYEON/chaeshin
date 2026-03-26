# Security Policy

[한국어](docs/ko/SECURITY.md)

## Security Considerations

Chaeshin is a framework that executes tools based on LLM output. Please be aware of the following security considerations.

### LLM Output Reliability

- Always **validate** that LLM-generated graphs (replan) are valid
- Use `max_loops` to prevent infinite loops (default: 3)
- `GraphExecutor` automatically blocks calls to non-existent tools

### API Key Management

- Store API keys in `.env` files
- **Never** commit `.env` files to Git
- Refer to `.env.example` for required environment variables

### Tool Execution Isolation

- **Restrict** system command execution in tool `executor` functions
- **Validate** user inputs passed as tool parameters
- In production, we recommend running tool execution in a sandbox

### Case Store

- Ensure CBR cases do not contain sensitive personal information
- Apply case anonymization for sensitive domains (medical, financial, etc.)
- Manage VectorDB access permissions appropriately

## Reporting Vulnerabilities

If you discover a security vulnerability, please contact us **privately** instead of opening a public issue:

- Email: contact@geohyeon.com
- Subject: `[SECURITY] Chaeshin Vulnerability Report`

We will respond within 48 hours.

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.1.x   | ✅ Yes    |
