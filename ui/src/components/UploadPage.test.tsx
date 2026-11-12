import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { UploadLinkError, fetchUploadLink, sendUploadLinkFile } from '../services/uploadLink';
import { UploadLinkInfo } from '../types';
import { UploadPage } from './UploadPage';

vi.mock('../services/uploadLink', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../services/uploadLink')>();
  return { ...actual, fetchUploadLink: vi.fn(), sendUploadLinkFile: vi.fn() };
});

const ID = '8f3c1d2e-4b5a-4c6d-9e8f-0a1b2c3d4e5f';
const credentials = { id: ID, token: 'vvupl_secret' };

const linkInfo = (overrides: Partial<UploadLinkInfo> = {}): UploadLinkInfo => ({
  id: ID,
  state: 'pending',
  title: 'Weekly sync',
  filename: null,
  expected_size_bytes: null,
  max_bytes: 1000,
  expires_at: '2026-11-12T13:00:00Z',
  entry_id: null,
  supported_formats: ['mp3', 'wav'],
  ...overrides,
});

const uploaded = {
  status: 'uploaded' as const,
  upload_id: ID,
  entry: { id: 'e1', title: 'Weekly sync' } as never,
};

const chooseFile = (name: string, size = 10) =>
  fireEvent.change(screen.getByLabelText('Choose a file'), {
    target: { files: [new File([new Uint8Array(size)], name)] },
  });

const openPage = (hash = `#${ID}.vvupl_secret`) => {
  window.history.replaceState(null, '', `/upload${hash}`);
  return render(<UploadPage />);
};

describe('UploadPage', () => {
  beforeEach(() => {
    vi.mocked(fetchUploadLink).mockReset();
    vi.mocked(sendUploadLinkFile).mockReset();
  });

  afterEach(() => window.history.replaceState(null, '', '/'));

  it('explains an incomplete link without calling the API', () => {
    openPage('');

    expect(screen.getByText('This upload link is incomplete')).toBeInTheDocument();
    expect(fetchUploadLink).not.toHaveBeenCalled();
  });

  it('uploads a chosen file and confirms it', async () => {
    vi.mocked(fetchUploadLink).mockResolvedValue(linkInfo());
    let report: (fraction: number) => void = () => {};
    let finish: (value: typeof uploaded) => void = () => {};
    vi.mocked(sendUploadLinkFile).mockImplementation((_creds, _file, onProgress) => {
      report = onProgress;
      return new Promise((resolve) => {
        finish = resolve;
      });
    });

    openPage();

    expect(await screen.findByText('For “Weekly sync”')).toBeInTheDocument();
    expect(fetchUploadLink).toHaveBeenCalledWith(credentials);
    // the secret leaves the address bar once read
    expect(window.location.hash).toBe('');

    chooseFile('notes.txt');
    expect(screen.getByRole('alert')).toHaveTextContent('Unsupported file type');
    expect(screen.getByRole('button', { name: 'Upload' })).toBeDisabled();

    chooseFile('standup.mp3');
    fireEvent.click(screen.getByRole('button', { name: 'Upload' }));
    expect(sendUploadLinkFile).toHaveBeenCalledWith(
      credentials,
      expect.objectContaining({ name: 'standup.mp3' }),
      expect.any(Function),
    );

    act(() => report(0.5));
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '50');

    await act(async () => finish(uploaded));
    expect(screen.getByText('Upload complete')).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('“Weekly sync” is being transcribed');
  });

  it('keeps the file for a retry after a network failure', async () => {
    vi.mocked(fetchUploadLink).mockResolvedValue(linkInfo());
    vi.mocked(sendUploadLinkFile)
      .mockRejectedValueOnce(new UploadLinkError(0, 'The connection was interrupted'))
      .mockResolvedValueOnce(uploaded);

    openPage();
    await screen.findByText('For “Weekly sync”');
    chooseFile('standup.mp3');
    fireEvent.click(screen.getByRole('button', { name: 'Upload' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('The connection was interrupted');
    // the error is about the attempt, not the file: the same file can be sent again
    const retry = screen.getByRole('button', { name: 'Try again' });
    expect(retry).toBeEnabled();
    fireEvent.click(retry);

    expect(await screen.findByText('Upload complete')).toBeInTheDocument();
    expect(sendUploadLinkFile).toHaveBeenCalledTimes(2);
  });

  it('stops for good when the link was used meanwhile', async () => {
    vi.mocked(fetchUploadLink).mockResolvedValue(linkInfo());
    vi.mocked(sendUploadLinkFile).mockRejectedValue(
      new UploadLinkError(409, 'This upload link was already used (entry e1)'),
    );

    openPage();
    await screen.findByText('For “Weekly sync”');
    chooseFile('standup.mp3');
    fireEvent.click(screen.getByRole('button', { name: 'Upload' }));

    expect(await screen.findByText('The upload could not be completed')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Upload' })).not.toBeInTheDocument();
  });

  it.each([
    ['expired', 'This upload link has expired'],
    ['completed', 'This upload link was already used'],
    ['uploading', 'An upload for this link is in progress'],
  ] as const)('shows a %s link as closed', async (state, title) => {
    vi.mocked(fetchUploadLink).mockResolvedValue(linkInfo({ state }));

    openPage();

    expect(await screen.findByText(title)).toBeInTheDocument();
    expect(screen.queryByLabelText('Choose a file')).not.toBeInTheDocument();
  });

  it('explains invalid links and offers a retry when unreachable', async () => {
    vi.mocked(fetchUploadLink).mockRejectedValueOnce(new UploadLinkError(401, 'invalid'));
    openPage();
    expect(await screen.findByText('This upload link is not valid')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Try again' })).not.toBeInTheDocument();
  });

  it('retries loading after a network error', async () => {
    vi.mocked(fetchUploadLink)
      .mockRejectedValueOnce(new UploadLinkError(0, 'VoiceVault could not be reached.'))
      .mockResolvedValueOnce(linkInfo());

    openPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Try again' }));

    expect(await screen.findByLabelText('Choose a file')).toBeInTheDocument();
  });
});
