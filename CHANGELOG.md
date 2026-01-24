# Changelog

All notable changes to the Multi-Agent AI Orchestrator will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.2.0] - 2026-01-24

### Added

#### Async URL Responses with 30-Day Retention 🆕
- **Asynchronous Job Processing**: Submit questions and receive a unique, shareable URL immediately without waiting for completion
- **Persistent Storage**: All results are stored in a database and accessible for 30 days
- **Database Integration**:
  - SQLAlchemy ORM with async support (aiosqlite/PostgreSQL compatible)
  - Automatic database initialization on startup
  - Comprehensive job schema: id, url_slug, question, status, response_content, error_message, timestamps, expiration
- **Job Lifecycle Management**:
  - Four job states: QUEUED, RUNNING, COMPLETED, FAILED
  - Background job processing with JobProcessor class
  - Automatic status updates throughout the job lifecycle
  - Job retry mechanism for failed jobs
- **30-Day Retention Policy**:
  - Jobs automatically expire after 30 days (configurable)
  - Periodic cleanup task runs hourly to delete expired jobs
  - 410 Gone response for expired URLs with user-friendly message
- **New API Endpoints**:
  - `POST /web-ask-async` - Submit async job and get unique URL
  - `GET /api/result/{url_slug}` - Get job status and result (JSON API)
  - `GET /result/{url_slug}` - View result page (HTML)
  - `POST /api/result/{url_slug}/retry` - Retry failed job
  - `GET /admin/job-stats` - Get job statistics for monitoring
- **Enhanced Web Interface**:
  - Async mode toggle (enabled by default)
  - Real-time status display with polling (3-second intervals)
  - Shareable URL display with copy-to-clipboard button
  - Status badges (queued, running, completed, failed, expired)
  - Automatic polling and status updates
  - Retry button for failed jobs
  - URL-based result viewing (shareable links)
- **Security Features**:
  - Cryptographically secure URL slug generation (12-char, ~72 bits entropy)
  - Unguessable URLs prevent unauthorized access
  - CSRF protection for all mutation endpoints
  - Feature flag for safe rollout (`ENABLE_ASYNC_JOBS`)
- **Monitoring and Logging**:
  - Comprehensive logging throughout job lifecycle
  - Job statistics endpoint for monitoring queues
  - Error tracking and reporting
  - Background task health monitoring
- **Configuration Options**:
  - `ENABLE_ASYNC_JOBS` - Enable/disable async processing (default: true)
  - `ASYNC_JOB_RETENTION_DAYS` - Retention period (default: 30 days)
  - `DATABASE_URL` - Database connection string (default: SQLite)
  - `SQL_DEBUG` - Enable SQL query logging (default: false)

### Changed
- **Application Version**: Updated from 1.1.0 to 1.2.0
- **Dependencies**: Added SQLAlchemy 2.0+, Alembic 1.13+, aiosqlite 0.19+
- **Health Endpoint**: Now includes `async_jobs_enabled` status in response
- **Frontend**: Added async mode toggle and status display components
- **Orchestration**: Created wrapper function for background job compatibility

### Fixed
- Improved error handling for async job processing
- Better handling of job failures with detailed error messages
- Enhanced cleanup of expired jobs with automatic scheduling

### Technical Details
- **New Modules**:
  - `database.py` - SQLAlchemy models, database initialization, job CRUD operations
  - `job_processor.py` - Background job processor with retry logic
  - `tests/test_async_jobs.py` - Comprehensive test suite for async jobs
- **Database Schema**:
  - AsyncJob model with full lifecycle tracking
  - Indexes on url_slug, status, and expires_at for performance
  - Timestamp tracking: created_at, started_at, completed_at, expires_at, last_updated
- **Pydantic Models**:
  - `AsyncJobSubmitResponse` - Response when submitting async job
  - `AsyncJobStatusResponse` - Response for status/result queries
- **Background Tasks**:
  - Startup event handler for database initialization
  - Periodic cleanup task using asyncio.create_task
  - Job processing using FastAPI BackgroundTasks (upgradeable to Celery)
- **Frontend Enhancements**:
  - New JavaScript functions for async workflow
  - Real-time polling with 3-second intervals
  - URL history management with pushState
  - Automatic result page detection on load
  - Status badge color coding

### Documentation
- Updated README.md with comprehensive async job documentation
- Added new section "Async URL Responses (v1.2.0)" with:
  - How it works explanation
  - Feature list and capabilities
  - API endpoint documentation with examples
  - Usage tips and best practices
  - Configuration table updates
  - Database schema documentation
- Updated CHANGELOG.md with detailed v1.2.0 release notes
- Updated .env.example with async job configuration

### Database
- **Initial Schema**: Created async_jobs table with complete lifecycle tracking
- **Migration Ready**: Structure designed for easy migration to PostgreSQL in production
- **Automatic Cleanup**: Hourly task removes expired jobs to prevent database growth

### Performance
- Background processing prevents blocking web server
- Concurrent job execution possible
- Database indexes optimize slug and status lookups
- Efficient polling with minimal overhead

### Reliability
- Robust error handling with detailed error messages
- Automatic retry mechanism for transient failures
- Job state persistence survives server restarts
- Expiration handling prevents stale data accumulation

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
