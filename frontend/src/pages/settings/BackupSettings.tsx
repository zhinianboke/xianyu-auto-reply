import { BackupSection, SettingsPageShell, SettingsResourceBoundary, useSettingsResource } from './SettingsShared'

export function BackupSettings() {
  const resource = useSettingsResource()

  return (
    <SettingsResourceBoundary resource={resource}>
      <SettingsPageShell>
        <BackupSection />
      </SettingsPageShell>
    </SettingsResourceBoundary>
  )
}
