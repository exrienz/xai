# Changelog

All notable changes to the Multi-Agent AI Orchestrator will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] - 2026-01-23

### Added

#### Follow-up Questions Feature 🆕
- **Multi-turn Conversations**: Users can now ask follow-up questions after receiving the "## 3. Synthesis & Final Verdict" without losing context
- **Automatic Context Preservation**: Follow-up questions are automatically seeded with the previous verdict content
- **Conversation Management**:
  - In-memory conversation storage (designed for future database compatibility)
  - Unique conversation IDs for tracking conversation chains
  - Parent-child conversation linking for maintaining conversation history
  - Automatic conversation cleanup (configurable timeout, default 24 hours)
- **New API Endpoints**:
  - `POST /web-followup` - Submit follow-up questions with context
  - `GET /conversation/{conversation_id}` - Retrieve conversation history
- **Enhanced Web Interface**:
  - Follow-up input section that appears automatically after verdict
  - Visual conversation badge indicating active conversation context
  - Keyboard shortcut support (Ctrl+Enter to submit follow-up)
  - Smooth animations and user feedback for follow-up interactions
- **Smart Context Management**:
  - Intelligent context truncation to prevent excessive prompt growth
  - Configurable context length limits (default 8000 characters)
  - Verdict extraction and caching for efficient context retrieval
- **Feature Flag Support**:
  - Environment variable `ENABLE_FOLLOWUP_QUESTIONS` for safe rollout (default: enabled)
  - Health endpoint updated to include feature status
- **Configuration Options**:
  - `MAX_CONVERSATION_CONTEXT_LENGTH` - Control context size (default: 8000 chars)
  - `CONVERSATION_TIMEOUT_HOURS` - Auto-cleanup timeout (default: 24 hours)
- **Enhanced Logging**:
  - Detailed logging for conversation creation and follow-up processing
  - Conversation ID tracking in logs for debugging
  - Automatic cleanup logging for monitoring

### Changed
- **Application Version**: Updated from 1.0.0 to 1.1.0
- **Web Response Model**: Added optional `conversation_id` field to `WebResponse`
- **Orchestration Function**: Enhanced `orchestrate()` function to accept optional context parameter
- **Frontend Notice**: Updated "New Question" notice to mention follow-up capability
- **Health Endpoint**: Now includes `followup_enabled` status in response

### Fixed
- Improved error handling for conversation context retrieval
- Enhanced fallback behavior when parent conversation is not found
- Better handling of edge cases in verdict extraction

### Technical Details
- Added `uuid` and `datetime` imports for conversation management
- Implemented conversation storage as in-memory dict (easily migrateable to database)
- Created Pydantic models: `Conversation`, `ConversationMessage`, `FollowUpRequest`, `FollowUpResponse`
- Added comprehensive helper functions for conversation CRUD operations
- Frontend state management enhanced with `currentConversationId` tracking

### Documentation
- Updated README.md with comprehensive follow-up questions documentation
- Added new section explaining how follow-up questions work
- Documented new API endpoints and their request/response formats
- Added usage tips and limitations for follow-up feature
- Updated configuration table with new environment variables

### Security
- CSRF protection maintained for follow-up endpoint
- Conversation isolation ensures no cross-user data leakage
- Automatic cleanup prevents indefinite memory growth

## [1.0.0] - 2026-01-XX

### Initial Release
- Multi-agent orchestration system
- Intelligent agent planning and execution
- Parallel agent execution for improved performance
- Robust fallback system with censorship detection
- Web UI with modern, responsive design
- REST API for programmatic access
- Configurable model pools
- CSRF protection for web interface
