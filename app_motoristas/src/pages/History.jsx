import React, { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import axios from 'axios'
import { ArrowLeft, Copy, CheckCircle } from 'lucide-react'
import { API_BASE_URL } from '../config'

export default function History({ user }) {
  const navigate = useNavigate()
  const [history, setHistory] = useState([])
  const [loading, setLoading] = useState(true)
  const [copiedId, setCopiedId] = useState(null)

  useEffect(() => {
    fetchHistory()
  }, [])

  const fetchHistory = async () => {
    try {
      const res = await axios.get(`${API_BASE_URL}/historico/${user.id_motorista}`)
      setHistory(res.data.historico || [])
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  const handleCopy = (text, id) => {
    if (!text) return
    navigator.clipboard.writeText(text)
    setCopiedId(id)
    setTimeout(() => setCopiedId(null), 2000)
  }

  return (
    <div className="container">
      <header className="app-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <button onClick={() => navigate('/')} style={{ background: 'none', border: 'none', color: 'white', cursor: 'pointer' }}>
            <ArrowLeft size={24} />
          </button>
          <h2 className="app-title" style={{ fontSize: '1.2rem', margin: 0 }}>Histórico de ATs</h2>
        </div>
      </header>

      <div style={{ flex: 1, overflowY: 'auto', paddingBottom: '20px' }}>
        {loading ? (
          <div style={{ display: 'flex', justifyContent: 'center', marginTop: '40px' }}>
            <div className="loader"></div>
          </div>
        ) : history.length === 0 ? (
          <p style={{ textAlign: 'center', color: 'var(--text-muted)', marginTop: '40px' }}>
            Nenhum pacote processado ainda.
          </p>
        ) : (
          history.map((item) => (
            <div key={item.id} className={`history-item ${item.status === 'SUCESSO' ? 'success' : 'error'}`}>
              <div className="history-header">
                <span>{item.data_hora}</span>
                <span style={{ color: item.status === 'SUCESSO' ? 'var(--success)' : 'var(--danger)', fontWeight: 'bold' }}>
                  {item.status}
                </span>
              </div>
              
              <div className="history-body">
                📦 {item.codigo_pacote}
              </div>

              {item.numero_at && (
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', background: 'rgba(0,0,0,0.2)', padding: '8px', borderRadius: '8px', marginTop: '4px' }}>
                  <span style={{ color: 'var(--primary)', fontWeight: 'bold', flex: 1 }}>{item.numero_at}</span>
                  <button 
                    onClick={() => handleCopy(item.numero_at, item.id)}
                    style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer' }}
                  >
                    {copiedId === item.id ? <CheckCircle size={18} color="var(--success)" /> : <Copy size={18} />}
                  </button>
                </div>
              )}

              <div className="history-footer" style={{ marginTop: '4px' }}>
                {item.mensagem.replace('✅ SUCESSO! ', '').replace('⚠️ ', '').replace('❌ ', '')}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  )
}
