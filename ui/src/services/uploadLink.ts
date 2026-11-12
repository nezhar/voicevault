import { UploadLinkCompleted, UploadLinkInfo } from '../types';
import { formatBytes } from '../utils/format';

// Upload links authenticate with their own token only. These calls bypass the
// shared axios client on purpose: it would attach a stored login token and
// redirect to the login screen on 401, neither of which applies here.

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const TOKEN_MARKER = 'vvupl_';

export interface UploadLinkCredentials {
  id: string;
  token: string;
}

export class UploadLinkError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = 'UploadLinkError';
  }
}

/** Reads `#<upload id>.<token>` as produced by the upload_file MCP tool. */
export const parseUploadFragment = (hash: string): UploadLinkCredentials | null => {
  const value = hash.replace(/^#/, '');
  const dot = value.indexOf('.');
  if (dot < 0) {
    return null;
  }
  const id = value.slice(0, dot);
  const token = value.slice(dot + 1);
  if (!UUID_PATTERN.test(id) || !token.startsWith(TOKEN_MARKER) || token === TOKEN_MARKER) {
    return null;
  }
  return { id, token };
};

const extensionOf = (name: string): string => {
  const dot = name.lastIndexOf('.');
  return dot > 0 ? name.slice(dot + 1).toLowerCase() : '';
};

/** The server checks all of this again; checking first saves a doomed upload. */
export const checkUploadFile = (file: File, info: UploadLinkInfo): string | null => {
  if (!info.supported_formats.includes(extensionOf(file.name))) {
    return `Unsupported file type. Supported: ${info.supported_formats.join(', ')}`;
  }
  if (file.size === 0) {
    return 'The selected file is empty.';
  }
  if (info.expected_size_bytes !== null && file.size !== info.expected_size_bytes) {
    return `This link expects a file of exactly ${formatBytes(info.expected_size_bytes)}; the selected file has ${formatBytes(file.size)}.`;
  }
  if (file.size > info.max_bytes) {
    return `The file is too large (maximum ${formatBytes(info.max_bytes)}).`;
  }
  return null;
};

const detailOf = (body: unknown): string | null => {
  if (body && typeof body === 'object' && 'detail' in body) {
    const { detail } = body as { detail: unknown };
    return typeof detail === 'string' ? detail : null;
  }
  return null;
};

export const fetchUploadLink = async ({
  id,
  token,
}: UploadLinkCredentials): Promise<UploadLinkInfo> => {
  let response: Response;
  try {
    response = await fetch(`/api/uploads/${id}`, {
      headers: { Authorization: `Bearer ${token}` },
      credentials: 'omit',
    });
  } catch {
    throw new UploadLinkError(0, 'VoiceVault could not be reached. Check your connection.');
  }
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    throw new UploadLinkError(
      response.status,
      detailOf(body) ?? `Request failed (${response.status})`,
    );
  }
  return body as UploadLinkInfo;
};

export const sendUploadLinkFile = (
  { id, token }: UploadLinkCredentials,
  file: File,
  onProgress: (fraction: number) => void,
): Promise<UploadLinkCompleted> =>
  // XMLHttpRequest rather than fetch: only it reports upload progress.
  new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('PUT', `/api/uploads/${id}?filename=${encodeURIComponent(file.name)}`);
    xhr.setRequestHeader('Authorization', `Bearer ${token}`);
    if (file.type) {
      xhr.setRequestHeader('Content-Type', file.type);
    }
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && event.total > 0) {
        onProgress(event.loaded / event.total);
      }
    };
    xhr.onload = () => {
      let body: unknown = null;
      try {
        body = JSON.parse(xhr.responseText);
      } catch {
        // proxy error pages are not JSON
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(body as UploadLinkCompleted);
      } else {
        reject(new UploadLinkError(xhr.status, detailOf(body) ?? `Upload failed (${xhr.status})`));
      }
    };
    xhr.onerror = () =>
      reject(
        new UploadLinkError(
          0,
          'The connection was interrupted before the upload finished. The link is still valid; try again.',
        ),
      );
    xhr.send(file);
  });
