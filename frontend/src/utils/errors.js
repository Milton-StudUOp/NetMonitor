export function getApiErrorMessage(err) {
  if (err.code === 'ECONNABORTED') {
    return 'The request timed out. Confirm that the NetMonitor backend is running and that the database is reachable.';
  }
  if (!err.response && err.request) {
    return 'The NetMonitor backend is unavailable. Verify the service, reverse proxy, and network connection.';
  }
  const detail = err.response?.data?.detail;

  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        const path = Array.isArray(item.loc) ? item.loc.join('.') : item.loc;
        return path ? `${path}: ${item.msg}` : item.msg;
      })
      .join('\n');
  }

  if (detail && typeof detail === 'object') {
    return JSON.stringify(detail);
  }

  return detail || err.message || 'Unknown error';
}
