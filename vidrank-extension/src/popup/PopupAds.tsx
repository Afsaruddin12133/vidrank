import { AdsOnBreadSlot } from '@adsonbread/react'

export function PopupAds() {
  const getLanguage = () => {
    try {
      if (typeof chrome !== 'undefined' && chrome.i18n && typeof chrome.i18n.getUILanguage === 'function') {
        return chrome.i18n.getUILanguage()
      }
    } catch {
      // fallback
    }
    return typeof navigator !== 'undefined' ? navigator.language : 'en'
  }

  return (
    <div
      className="popup-ads-container"
      style={{
        width: '100%',
        display: 'flex',
        justifyContent: 'center',
        margin: '10px 0',
        minHeight: '64px',
      }}
    >
      <AdsOnBreadSlot
        apiKey="b5b7a45f-7690-472e-81f3-feffe29804e3"
        placement="banner"
        theme="light"
        language={getLanguage()}
        fallback={null}
        onAdLoad={(ad) => console.log('[AdsOnBread] Ad loaded successfully:', ad)}
        onError={(err) => console.warn('[AdsOnBread] Ad failed to load:', err)}
      />
    </div>
  )
}

export default PopupAds
