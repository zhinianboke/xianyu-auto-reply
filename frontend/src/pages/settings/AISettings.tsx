import { AiSettingsSection, SettingsActions, SettingsPageShell, SettingsResourceBoundary, useSettingsResource } from './SettingsShared'

export function AISettings() {
  const resource = useSettingsResource()

  return (
    <SettingsResourceBoundary resource={resource}>
      <SettingsPageShell
        actions={<SettingsActions onRefresh={resource.loadSettings} onSave={resource.handleSave} saving={resource.saving} />}
      >
        <AiSettingsSection />
      </SettingsPageShell>
    </SettingsResourceBoundary>
  )
}
