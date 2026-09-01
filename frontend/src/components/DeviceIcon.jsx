import React from 'react';
import { BatteryCharging, Box, Database, GitFork, Network, PanelsTopLeft,
  Radio, Router, Satellite, Server, Shield, Wifi } from 'lucide-react';

const ICONS = { Router, Network, Shield, Wifi, GitFork, Server, Box, Database, Radio,
  Satellite, BatteryCharging, PanelsTopLeft };

export default function DeviceIcon({ icon, size = 20, color = 'currentColor' }) {
  if (icon?.custom_data) {
    const source = icon.mime_type === 'image/png'
      ? `data:image/png;base64,${icon.custom_data}`
      : `data:image/svg+xml;charset=utf-8,${encodeURIComponent(icon.custom_data)}`;
    return <img src={source} alt="" style={{ width: size, height: size, objectFit: 'contain' }} />;
  }
  const Component = ICONS[icon?.lucide_name] || Server;
  return <Component size={size} color={color} />;
}
