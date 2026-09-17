import React, { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { Html5Qrcode } from 'html5-qrcode'
import axios from 'axios'
import { LogOut, History, Camera, Search, X } from 'lucide-react'
import { API_BASE_URL } from '../config'

export default function Dashboard({ user, onLogout }) {
  const navigate = useNavigate()
  const [manualCode, setManualCode] = useState('')
  const [loading, setLoading] = useState(false)
  const [toast, setToast] = useState(null)
  const [scannerActive, setScannerActive] = useState(false)
  const html5QrCode = useRef(null)

  useEffect(() => {
    return () => {
      stopScanner()
    }
  }, [])

  const startScanner = async () => {
    setScannerActive(true)
    try {
      html5QrCode.current = new Html5Qrcode("reader")
      await html5QrCode.current.start(
        { facingMode: "environment" },
        { fps: 10, qrbox: { width: 250, height: 100 } },
        (decodedText) => {
          stopScanner()
          handleProcessCode(decodedText)
        },
        (errorMessage) => {
          // Ignorar erros de leitura de frame vazio
        }
      )
    } catch (err) {
      console.error(err)
      showToast('Erro ao acessar a câmera.', 'error')
      setScannerActive(false)
    }
  }

  const stopScanner = async () => {
    if (html5QrCode.current && html5QrCode.current.isScanning) {
      try {
        await html5QrCode.current.stop()
        html5QrCode.current.clear()
      } catch (err) {
        console.error(err)
      }
    }
    setScannerActive(false)
  }

  const showToast = (msg, type) => {
    setToast({ msg, type })
    setTimeout(() => setToast(null), 5000)
  }

  const handleProcessCode = async (codeToProcess) => {
    const finalCode = codeToProcess || manualCode
    if (!finalCode) return

    setLoading(true)
    try {
      const res = await axios.post(`${API_BASE_URL}/gerar_at`, {
        id_motorista: user.id_motorista,
        codigo_pacote: finalCode
      })
      if (res.data.sucesso) {
        showToast(res.data.mensagem, 'success')
      } else {
        showToast(res.data.mensagem, 'error')
      }
      setManualCode('') // Clear input
    } catch (err) {
      showToast(err.response?.data?.detail || 'Erro de comunicação com o servidor.', 'error')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="container">
      <header className="app-header">
        <div>
          <h1 className="app-title">Olá, {user.nome.split(' ')[0]}</h1>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}>Pronto para gerar ATs!</p>
        </div>
        <div style={{ display: 'flex', gap: '12px' }}>
          <button onClick={() => navigate('/history')} style={{ background: 'none', border: 'none', color: 'white', cursor: 'pointer' }}>
            <History size={24} />
          </button>
          <button onClick={onLogout} style={{ background: 'none', border: 'none', color: 'var(--danger)', cursor: 'pointer' }}>
            <LogOut size={24} />
          </button>
        </div>
      </header>

      <div className="card" style={{ flex: 1, justifyContent: 'center' }}>
        
        {!scannerActive ? (
          <button className="btn" style={{ padding: '24px', fontSize: '1.2rem', marginBottom: '20px' }} onClick={startScanner}>
            <Camera size={28} />
            Escanear Código
          </button>
        ) : (
          <div style={{ position: 'relative', marginBottom: '20px' }}>
            <div id="reader"></div>
            <button 
              onClick={stopScanner}
              style={{ position: 'absolute', top: 10, right: 10, background: 'var(--danger)', color: 'white', border: 'none', borderRadius: '50%', width: '40px', height: '40px', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer' }}
            >
              <X size={20} />
            </button>
            <p style={{ textAlign: 'center', color: 'var(--text-muted)', marginTop: '8px', fontSize: '0.9rem' }}>
              Aponte a câmera para o código de barras
            </p>
          </div>
        )}

        <div style={{ textAlign: 'center', color: 'var(--text-muted)', margin: '10px 0' }}>OU</div>

        <div className="input-group">
          <label>Digitar Manualmente</label>
          <input 
            type="text" 
            className="input-field" 
            placeholder="BR..." 
            value={manualCode}
            onChange={(e) => setManualCode(e.target.value)}
          />
        </div>
        
        <button 
          className="btn btn-secondary" 
          onClick={() => handleProcessCode()} 
          disabled={loading || !manualCode}
          style={{ marginTop: '10px' }}
        >
          {loading ? <div className="loader"></div> : <><Search size={20} /> Buscar e Gerar AT</>}
        </button>

      </div>

      {toast && (
        <div className="toast" style={{ borderColor: toast.type === 'error' ? 'var(--danger)' : 'var(--success)' }}>
          {toast.msg}
        </div>
      )}
    </div>
  )
}
