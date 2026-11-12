import { afterEach, describe, expect, it, vi } from 'vitest';

import { UploadLinkInfo } from '../types';
import {
  UploadLinkError,
  checkUploadFile,
  fetchUploadLink,
  parseUploadFragment,
  sendUploadLinkFile,
} from './uploadLink';

const ID = '8f3c1d2e-4b5a-4c6d-9e8f-0a1b2c3d4e5f';
const credentials = { id: ID, token: 'vvupl_secret' };

const info = (overrides: Partial<UploadLinkInfo> = {}): UploadLinkInfo => ({
  id: ID,
  state: 'pending',
  title: null,
  filename: null,
  expected_size_bytes: null,
  max_bytes: 100,
  expires_at: '2026-11-12T13:00:00Z',
  entry_id: null,
  supported_formats: ['mp3', 'wav'],
  ...overrides,
});

const fileOf = (name: string, size: number) => new File([new Uint8Array(size)], name);

describe('parseUploadFragment', () => {
  it('splits the upload id from the token', () => {
    expect(parseUploadFragment(`#${ID}.vvupl_a.b-c`)).toEqual({
      id: ID,
      token: 'vvupl_a.b-c',
    });
  });

  it('rejects incomplete or foreign fragments', () => {
    for (const hash of [
      '',
      '#',
      `#${ID}`,
      `#${ID}.`,
      `#${ID}.vvupl_`,
      `#${ID}.vvpat_x`,
      '#x.vvupl_y',
    ]) {
      expect(parseUploadFragment(hash)).toBeNull();
    }
  });
});

describe('checkUploadFile', () => {
  it('accepts a supported file within the limits', () => {
    expect(checkUploadFile(fileOf('talk.MP3', 10), info())).toBeNull();
  });

  it('explains what is wrong with the file', () => {
    expect(checkUploadFile(fileOf('notes.txt', 10), info())).toMatch(/Unsupported file type/);
    expect(checkUploadFile(fileOf('mp3', 10), info())).toMatch(/Unsupported file type/);
    expect(checkUploadFile(fileOf('a.mp3', 0), info())).toMatch(/empty/);
    expect(checkUploadFile(fileOf('a.mp3', 101), info())).toMatch(/too large/);
    expect(
      checkUploadFile(fileOf('a.mp3', 10), info({ expected_size_bytes: 12, max_bytes: 12 })),
    ).toMatch(/expects a file of exactly/);
  });
});

describe('fetchUploadLink', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('authenticates with the link token only', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(info())));
    vi.stubGlobal('fetch', fetchMock);

    await expect(fetchUploadLink(credentials)).resolves.toMatchObject({ id: ID });
    expect(fetchMock).toHaveBeenCalledWith(`/api/uploads/${ID}`, {
      headers: { Authorization: 'Bearer vvupl_secret' },
      credentials: 'omit',
    });
  });

  it('surfaces the server detail and status', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue(
          new Response(JSON.stringify({ detail: 'This upload link has expired' }), { status: 410 }),
        ),
    );

    const error = await fetchUploadLink(credentials).catch((err: unknown) => err);
    expect(error).toBeInstanceOf(UploadLinkError);
    expect(error).toMatchObject({ status: 410, message: 'This upload link has expired' });
  });
});

class FakeXHR {
  static last: FakeXHR;
  method = '';
  url = '';
  headers: Record<string, string> = {};
  body: unknown;
  status = 0;
  responseText = '';
  upload: { onprogress?: (event: Partial<ProgressEvent>) => void } = {};
  onload?: () => void;
  onerror?: () => void;

  constructor() {
    FakeXHR.last = this;
  }

  open(method: string, url: string) {
    this.method = method;
    this.url = url;
  }

  setRequestHeader(name: string, value: string) {
    this.headers[name] = value;
  }

  send(body: unknown) {
    this.body = body;
  }

  respond(status: number, body: unknown) {
    this.status = status;
    this.responseText = typeof body === 'string' ? body : JSON.stringify(body);
    this.onload?.();
  }
}

describe('sendUploadLinkFile', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('PUTs the raw file with its name and reports progress', async () => {
    vi.stubGlobal('XMLHttpRequest', FakeXHR);
    const file = new File(['abc'], 'Board meeting.mp3', { type: 'audio/mpeg' });
    const progress = vi.fn();

    const pending = sendUploadLinkFile(credentials, file, progress);
    const xhr = FakeXHR.last;
    xhr.upload.onprogress?.({ lengthComputable: true, loaded: 1, total: 4 });
    xhr.respond(200, { status: 'uploaded', upload_id: ID, entry: { title: 'Board meeting' } });

    await expect(pending).resolves.toMatchObject({ entry: { title: 'Board meeting' } });
    expect(xhr.method).toBe('PUT');
    expect(xhr.url).toBe(`/api/uploads/${ID}?filename=Board%20meeting.mp3`);
    expect(xhr.headers).toEqual({
      Authorization: 'Bearer vvupl_secret',
      'Content-Type': 'audio/mpeg',
    });
    expect(xhr.body).toBe(file);
    expect(progress).toHaveBeenCalledWith(0.25);
  });

  it('rejects with the status for server errors and 0 for network failures', async () => {
    vi.stubGlobal('XMLHttpRequest', FakeXHR);
    const file = new File(['abc'], 'a.mp3');

    const rejected = sendUploadLinkFile(credentials, file, vi.fn());
    FakeXHR.last.respond(413, '<html>Request Entity Too Large</html>');
    await expect(rejected).rejects.toMatchObject({ status: 413, message: 'Upload failed (413)' });

    const interrupted = sendUploadLinkFile(credentials, file, vi.fn());
    FakeXHR.last.onerror?.();
    await expect(interrupted).rejects.toMatchObject({ status: 0 });
  });
});
