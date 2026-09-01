export function getApiErrorMessage(err) {
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
