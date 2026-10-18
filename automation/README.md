# Reel Generator Automation System
# ===============================

## Overview

This automation system transforms your existing Reel Generator into a fully automated weekly content pipeline. It generates and publishes 2 Reels per week (Tuesday and Saturday) to both YouTube Shorts and Instagram Reels without manual intervention.

## Quick Start

### 1. Setup
```bash
# Run the automation setup
setup_automation.bat

# Edit your API credentials
copy .env.example .env
# Edit .env file with your actual API keys
```

### 2. Test the Pipeline
```bash
# Test in dry-run mode (no actual publishing)
python automation/run_pipeline.py --dry-run

# Test with specific topic
python automation/run_pipeline.py --topic "What is Quantum Computing" --dry-run
```

### 3. Run Automatically
```bash
# Run Tuesday schedule
python automation/run_pipeline.py --schedule tuesday

# Run Saturday schedule  
python automation/run_pipeline.py --schedule saturday

# Run both schedules
python automation/run_pipeline.py --schedule both
```

## Architecture

The automation system coordinates these components:

```
Topic Planner → Generator → Validator → YouTube Publisher → Instagram Publisher
     ↓              ↓         ↓            ↓              ↓
  Deduplication   Script   Quality     API Upload     API Upload
  Selection       Gen      Checks      OAuth2         Graph API
```

## Key Features

### 🎯 Smart Topic Selection
- **Deduplication**: Prevents similar topics
- **Category Rotation**: Ensures content variety
- **Recent Tracking**: Avoids duplicate content
- **Fallback Pool**: Predefined topics if LLM fails

### 🎬 Complete Reel Generation
- Reuses existing generator pipeline
- **Script Generation**: LLM-powered script creation
- **Voice Synthesis**: Kokoro/Supertonic/Indic TTS
- **Image Scraping**: Automated web image collection
- **Video Composition**: Professional video assembly

### ✅ Quality Validation
- **File Validation**: Checks MP4 format, resolution, duration
- **Content Quality**: Audio/video stream verification
- **Size Limits**: Enforces file size constraints
- **Error Recovery**: Automatic retry mechanisms

### 📱 Multi-Platform Publishing
- **YouTube Shorts**: OAuth2 API integration
- **Instagram Reels**: Meta Graph API integration
- **Batch Publishing**: Publishes to both platforms
- **Retry Logic**: Handles API failures gracefully

### 📊 History & Recovery
- **SQLite Database**: Tracks all publishing attempts
- **Duplicate Prevention**: Avoids re-publishing
- **Recovery System**: Retries failed tasks
- **Statistics**: Success rates and performance metrics

## Configuration

### Environment Variables
Set these in your `.env` file:

```bash
# YouTube API
YOUTUBE_CLIENT_ID=your_client_id
YOUTUBE_CLIENT_SECRET=your_client_secret
YOUTUBE_REFRESH_TOKEN=your_refresh_token

# Instagram API
INSTAGRAM_ACCESS_TOKEN=your_access_token
INSTAGRAM_BUSINESS_ID=your_business_id
INSTAGRAM_APP_ID=your_app_id
INSTAGRAM_APP_SECRET=your_app_secret
```

### Configuration File
Edit `config/automation.yaml`:

```yaml
# Scheduling
schedule:
  tuesday_cron: "0 10 * * 2"    # Tuesday 10 AM
  saturday_cron: "0 10 * * 6"   # Saturday 10 AM
  timezone: "Asia/Kolkata"

# Generation settings
generation:
  content_type: "educational"
  duration_seconds: 60
  tts_engine: "kokoro"
  overlay: "oggy horizontal.mp4"
  use_intro: true

# Publishing settings
youtube:
  enabled: true
  privacy_status: "public"
  
instagram:
  enabled: true
  share_to_feed: true
```

## Usage Examples

### Testing
```bash
# Dry run (test without publishing)
python automation/run_pipeline.py --dry-run

# Test with specific topic
python automation/run_pipeline.py --topic "AI explained" --dry-run

# Check if should run based on schedule
python automation/run_pipeline.py --check-schedule
```

### Production
```bash
# Run scheduled pipeline
python automation/run_pipeline.py --schedule tuesday

# Retry failed publishing
python automation/run_pipeline.py --retry-failed

# Manual override with specific topic
python automation/run_pipeline.py --topic "Blockchain technology"
```

## Monitoring

### Log Files
- `logs/automation.log` - Main pipeline logs
- `outputs/script/reel_generator.log` - Generator logs

### Database Queries
```bash
# Check recent publishing history
sqlite3 data/publishing_history.db "SELECT topic, youtube_status, instagram_status, generated_at FROM published_reels ORDER BY generated_at DESC LIMIT 5"

# Check failed publishing attempts
sqlite3 data/publishing_history.db "SELECT topic, youtube_error, instagram_error FROM published_reels WHERE overall_status = 'failed'"
```

### Statistics
```bash
# Get publishing statistics
python -c "
from automation.pipeline.history_db import get_db
db = get_db()
stats = db.get_publishing_stats()
print(f'Total Reels: {stats[\"total_reels\"]}')
print(f'Published: {stats[\"published_reels\"]}')
print(f'Success Rate: {stats[\"success_rate\"]:.1f}%')
"
```

## Error Handling

### Common Issues

**API Authentication Failed**
```bash
# Check credentials in .env file
# Verify API permissions in Google/Meta consoles
```

**Video Generation Failed**
```bash
# Check disk space
# Verify dependencies: python -c "import moviepy, selenium, torch"
# Check logs: logs/automation.log
```

**Rate Limiting**
```bash
# System automatically retries with backoff
# Check API quotas in Google/Meta consoles
```

### Recovery Commands
```bash
# Retry all failed tasks
python automation/run_pipeline.py --retry-failed

# Reset database (start fresh)
del data\publishing_history.db

# Test individual components
python automation/run_pipeline.py --dry-run --topic "test topic"
```

## Scheduled Execution

### Using Windows Task Scheduler
1. Open Task Scheduler
2. Create Basic Task
3. Trigger: "Weekly" → Tuesday at 10:00 AM
4. Action: "Start a program" → `python.exe`
5. Arguments: `automation\run_pipeline.py --schedule tuesday`
6. Working Directory: Your project path
7. Repeat for Saturday

### Using Cron (if available)
```bash
# Add to crontab
0 10 * * 2 cd /path/to/reel && python automation/run_pipeline.py --schedule tuesday
0 10 * * 6 cd /path/to/reel && python automation/run_pipeline.py --schedule saturday
```

## Security

### Credentials
- Never commit `.env` file to git
- Use environment variables for API keys
- Regularly rotate API tokens
- Use app-specific passwords where possible

### Data Protection
- Database stores only metadata, not video files
- API tokens are encrypted at rest
- Logs do not contain sensitive information
- Regular cleanup of old records

## Performance

### Expected Performance
- **Generation Time**: 5-15 minutes per reel
- **Publishing Time**: 2-5 minutes per platform
- **Success Rate**: >90% generation, >80% publishing
- **Storage**: ~100MB per reel video

### Optimization Tips
- Use SSD storage for faster video processing
- Ensure stable internet connection
- Monitor API quotas
- Regular cleanup of old files

## Support

### Troubleshooting
1. Check `logs/automation.log` for error messages
2. Verify API credentials in `.env` file
3. Test individual components with `--dry-run`
4. Check disk space and permissions
5. Verify network connectivity

### Getting Help
- Review `automation/SKILL.md` for detailed documentation
- Check existing issues in project repository
- Monitor system statistics and logs
- Test in dry-run mode before production

## Roadmap

### Future Enhancements
- [ ] Multi-language support
- [ ] Advanced analytics dashboard
- [ ] Content calendar integration
- [ ] A/B testing for titles and thumbnails
- [ ] Cross-platform scheduling
- [ ] Mobile app notifications
- [ ] Custom watermark support
- [ ] Batch processing for multiple topics

---

**Remember**: This system is designed to run unattended. Always test in dry-run mode before enabling production publishing!