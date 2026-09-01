import axios from 'axios'

const API_BASE_URL = '/api'

export const api = {
  async createSession() {
    const response = await axios.post(`${API_BASE_URL}/sessions`)
    return response.data
  },

  async getLanguages() {
    const response = await axios.get(`${API_BASE_URL}/languages`)
    return response.data
  },
}
