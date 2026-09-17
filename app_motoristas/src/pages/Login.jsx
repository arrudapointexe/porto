import React, { useState } from 'react'
import axios from 'axios'
import { API_BASE_URL } from '../config'

export default function Login({ onLogin }) {
  const [isRegister, setIsRegister] = useState(false)
  const [formData, setFormData] = useState({ nome: '', login: '', senha: '' })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleChange = (e) => {
    setFormData({ ...formData, [e.target.name]: e.target.value })
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      if (isRegister) {
        await axios.post(`${API_BASE_URL}/register`, formData)
        // Login immediately after register
        const res = await axios.post(`${API_BASE_URL}/login`, { login: formData.login, senha: formData.senha })
        onLogin(res.data)
      } else {
        const res = await axios.post(`${API_BASE_URL}/login`, { login: formData.login, senha: formData.senha })
        onLogin(res.data)
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'Ocorreu um erro.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="container" style={{ justifyContent: 'center' }}>
      <div className="card">
        <h2 className="app-title" style={{ textAlign: 'center', marginBottom: '8px' }}>
          App Motoristas
        </h2>
        <p style={{ textAlign: 'center', color: 'var(--text-muted)', marginBottom: '20px' }}>
          {isRegister ? 'Crie sua conta para gerar ATs' : 'Faça login para gerar ATs'}
        </p>

        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {isRegister && (
            <div className="input-group">
              <label>Nome Completo</label>
              <input type="text" name="nome" className="input-field" value={formData.nome} onChange={handleChange} required />
            </div>
          )}
          <div className="input-group">
            <label>Login / Usuário</label>
            <input type="text" name="login" className="input-field" value={formData.login} onChange={handleChange} required />
          </div>
          <div className="input-group">
            <label>Senha</label>
            <input type="password" name="senha" className="input-field" value={formData.senha} onChange={handleChange} required />
          </div>
          
          {error && <div style={{ color: 'var(--danger)', fontSize: '0.9rem', textAlign: 'center' }}>{error}</div>}
          
          <button type="submit" className="btn" disabled={loading} style={{ marginTop: '8px' }}>
            {loading ? <div className="loader"></div> : (isRegister ? 'Cadastrar' : 'Entrar')}
          </button>
        </form>

        <div style={{ textAlign: 'center', marginTop: '16px' }}>
          <button 
            type="button" 
            onClick={() => setIsRegister(!isRegister)} 
            style={{ background: 'none', border: 'none', color: 'var(--primary)', cursor: 'pointer', fontSize: '0.95rem' }}>
            {isRegister ? 'Já tenho uma conta. Fazer Login' : 'Não tenho conta. Cadastrar'}
          </button>
        </div>
      </div>
    </div>
  )
}
