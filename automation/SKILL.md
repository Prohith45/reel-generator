# Hermes Skill: Reel Generator Automation
# =======================================

# SKILL.md for automated Reel generation and publishing pipeline

## Project Purpose
Automated weekly content pipeline that generates and publishes Reels to YouTube Shorts and Instagram every Tuesday and Saturday without manual intervention.

## Existing Generator Workflow
The automation system treats the existing Reel Generator as a production pipeline:

1. **Topic Selection** → Uses topic planner with deduplication
2. **Script Generation** → Calls existing `src/script_engine.py` 
3. **Voice Synthesis** → Uses existing TTS engines (Kokoro, Supertonic, Indic)
4. **Image Scraping** → Uses existing image scraping pipeline
5. **Video Composition** → Calls existing `src/video_engine.py`
6. **Validation** → Automated quality checks
7. **Publishing** → YouTube Shorts + Instagram Reels APIs

## How to Start Generation

### Manual Test Run
```bash
# Test the pipeline in dry-run mode (no actual publishing)
python automation/run_pipeline.py --dry-run

# Run with specific topic (bypasses topic planner)
python automation/run_pipeline.py --topic "What is Quantum Computing"

# Retry failed publishing tasks
python automation/run_pipeline.py --retry-failed
```

### Scheduled Execution
The system is designed to run automatically on schedule:
- **Tuesday**: 10:00 AM (Asia/Kolkata timezone)
- **Saturday**: 10:00 AM (Asia/Kolkata timezone)

## How to Validate Output

### Video Validation
The system automatically validates:
- File exists and is not empty
- Correct MP4 format (1080x1920 resolution)
- Duration within target range (±10%)
- Has audio and video streams
- File size limits (1MB-500MB)

### Publishing Validation
- Checks API response status
- Records video/media IDs
- Verifies URL accessibility
- Tracks publishing success/failure

## Where Credentials Are Configured

### YouTube API Credentials
Set via environment variables:
```bash
export YOUTUBE_CLIENT_ID="your_client_id"
export YOUTUBE_CLIENT_SECRET="your_client_secret" 
export YOUTUBE_REFRESH_TOKEN="your_refresh_token"
```

### Instagram API Credentials  
Set via environment variables:
```bash
export INSTAGRAM_ACCESS_TOKEN="your_access_token"
export INSTAGRAM_BUSINESS_ID="your_business_id"
export INSTAGRAM_APP_ID="your_app_id"
export INSTAGRAM_APP_SECRET="your_app_secret"
```

### Configuration File
`config/automation.yaml` contains:
- Scheduling settings
- Generation defaults
- Publisher configurations
- Quality control parameters

## Where History Is Stored

### Publishing Database
`data/publishing_history.db` - SQLite database tracking:
- Topic and metadata
- Video file paths
- YouTube video IDs/URLs
- Instagram media IDs/URLs
- Success/failure status
- Retry counts

### Cache Files
- `data/youtube_cache.json` - YouTube upload cache
- `data/instagram_cache.json` - Instagram upload cache
- `data/topics_database.json` - Topic selection database

## Recovery Procedures

### Failed Generation
1. System retries generation up to 2 times
2. Logs detailed error messages
3. Continues to publishing if generation succeeds
4. Skips publishing if generation fails completely

### Platform-Specific Failures
- **YouTube succeeds, Instagram fails**: Only retries Instagram
- **Instagram succeeds, YouTube fails**: Only retries YouTube  
- **Both fail**: Retries both platforms on next run

### Recovery Commands
```bash
# Retry all failed publishing tasks
python automation/run_pipeline.py --retry-failed

# Check pipeline status
python automation/run_pipeline.py --check-schedule

# Run specific schedule
python automation/run_pipeline.py --schedule tuesday
```

## Rules for Avoiding Duplicate Publishing

### Topic Deduplication
1. **Similarity Check**: Uses string similarity algorithm (threshold: 0.75)
2. **Recent Topics**: Checks last 20 published topics
3. **Category Rotation**: Ensures variety across content categories
4. **Usage Tracking**: Tracks topic frequency and avoids overuse

### Video Deduplication
1. **File-based Check**: Compares video filenames
2. **Metadata Check**: Compares titles and descriptions
3. **Platform Check**: Checks if same content already published

### Publishing Prevention
- Skips publishing if video already exists on platform
- Records all publishing attempts in database
- Prevents duplicate uploads to same account

## Pipeline Architecture

```
Topic Planner → Generator → Validator → YouTube Publisher → Instagram Publisher
     ↓              ↓         ↓            ↓              ↓
  Deduplication   Script   Quality     API Upload     API Upload
  Selection       Gen      Checks      OAuth2         Graph API
```

## Monitoring and Debugging

### Log Files
- `logs/automation.log` - Main pipeline logs
- `outputs/script/reel_generator.log` - Generator logs
- Check timestamps and error messages

### Status Commands
```bash
# Check recent pipeline runs
sqlite3 data/publishing_history.db "SELECT * FROM published_reels ORDER BY generated_at DESC LIMIT 5"

# Check topic database  
cat data/topics_database.json

# Check publisher status
python automation/run_pipeline.py --check-schedule
```

## Configuration Customization

### Modify Scheduling
Edit `config/automation.yaml`:
```yaml
schedule:
  tuesday_cron: "0 14 * * 2"    # Change to 2 PM
  saturday_cron: "0 14 * * 6"   # Change to 2 PM
  timezone: "America/New_York"  # Change timezone
```

### Modify Content Categories
Add topics to the fallback pool or modify generation defaults:
```yaml
generation:
  content_type: "technology"     # Focus on tech content
  duration_seconds: 90           # Longer videos
  tts_engine: "supertonic"       # Different voice
```

### Test Mode
Enable dry-run for testing:
```yaml
dry_run:
  enabled: true
```

## Error Scenarios and Solutions

### Common Issues
1. **API Authentication Failed**: Check credentials and permissions
2. **Video Generation Failed**: Check disk space and dependencies
3. **Rate Limiting**: Wait and retry automatically
4. **Network Issues**: System retries with exponential backoff

### Emergency Recovery
1. **Manual Override**: Use `--topic` to bypass topic planner
2. **Force Retry**: Use `--retry-failed` to retry all failures
3. **Reset Database**: Delete `data/publishing_history.db` to start fresh
4. **Test Mode**: Enable `dry_run: true` for safe testing

## Success Metrics

### Expected Output
- **2 Reels per week**: Tuesday + Saturday
- **Success Rate**: >90% for generation, >80% for publishing
- **Quality**: 1080x1920 MP4, 60 seconds, proper audio
- **Platforms**: YouTube Shorts + Instagram Reels

### Monitoring Dashboard
Track these metrics:
- Total published reels
- Success/failure rates  
- Average generation time
- Platform-specific performance
- Topic diversity metrics