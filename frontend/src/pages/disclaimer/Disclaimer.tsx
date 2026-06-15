/**
 * 免责声明页面
 */
import { DisclaimerContent } from '@/components/common/DisclaimerContent'

export function Disclaimer() {
  return (
    <div className="max-w-4xl mx-auto">
      <div className="vben-card">
        <div className="vben-card-header">
          <h1 className="vben-card-title">免责声明</h1>
        </div>
        <div className="vben-card-body">
          <DisclaimerContent />
        </div>
      </div>
    </div>
  )
}
