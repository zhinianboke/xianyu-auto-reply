import { SettingsActions, SettingsPageShell, SettingsResourceBoundary, SmtpSettingsSection, SystemSettingsSection, useSettingsResource } from './SettingsShared'

export function Settings() {
  const resource = useSettingsResource()

  return (
    <SettingsResourceBoundary resource={resource}>
      <SettingsPageShell
        actions={<SettingsActions onRefresh={resource.loadSettings} onSave={resource.handleSave} saving={resource.saving} />}
      >
        <div className="space-y-4">
          <SystemSettingsSection />
          <SmtpSettingsSection />
        </div>
      </SettingsPageShell>
    </SettingsResourceBoundary>
  )
}
