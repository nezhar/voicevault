# VoiceVault UI

Modern React frontend for VoiceVault enterprise voice intelligence platform.

## Features

- **Entry Management**: Create entries from URLs or file uploads
- **Real-time Status**: Live job status updates with polling
- **Chat Interface**: Interactive chat with processed transcripts (placeholder for future AI integration)
- **Responsive Design**: Clean, mobile-friendly interface using Tailwind CSS
- **Type Safety**: Full TypeScript support

## Tech Stack

- **React 18** with TypeScript
- **Vite** for fast development and building
- **Tailwind CSS** for styling
- **Lucide React** for icons
- **Axios** for API communication

## Development

```bash
# Install dependencies
npm install

# Start development server
npm run dev

# Build for production
npm run build
```

## API Integration

The UI communicates with the VoiceVault API at `/api` endpoints:

- `POST /api/entries/upload` - Upload audio/video files
- `POST /api/entries/url` - Create entry from URL
- `GET /api/entries` - List all entries with pagination
- `GET /api/entries/{id}` - Get specific entry

## Components

- **EntryForm**: Handles file uploads and URL submissions
- **EntryList**: Displays entries with status information
- **EntryCard**: Individual entry display with status badges
- **ChatInterface**: Modal chat interface for processed entries

## Status Flow

1. **NEW** - Entry created, queued for processing
2. **IN_PROGRESS** - Being processed by workers
3. **READY** - Transcript available, chat enabled
4. **ERROR** - Processing failed with error message

## Future Enhancements

- Real AI chat integration with transcript content
- Advanced filtering and search
- Batch operations
- Export functionality
- User management