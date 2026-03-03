/**
 * Testes E2E para o fix de timezone.
 *
 * Contexto: O backend envia datetimes UTC naive (ex: "2026-03-02T11:00:00").
 * Antes do fix, o browser interpretava como hora local, causando diff errado.
 * Agora o frontend trata strings sem Z/offset como UTC (via ensureUTC).
 */
import { describe, it, expect } from "vitest"
import { timeAgo, timeUntil, formatDate, formatDateTime } from "../utils"

// Helper: gera ISO string UTC naive (sem Z) para N minutos atras
function utcMinutesAgo(minutes: number): string {
  const d = new Date(Date.now() - minutes * 60_000)
  return d.toISOString().replace("Z", "")  // simula backend naive
}

// Helper: gera ISO string UTC naive para N minutos no futuro
function utcMinutesFromNow(minutes: number): string {
  const d = new Date(Date.now() + minutes * 60_000)
  return d.toISOString().replace("Z", "")
}

describe("Fix timezone: strings naive tratadas como UTC", () => {
  // =============================================
  // timeAgo — "Ultimo Check"
  // =============================================
  describe("timeAgo", () => {
    it("retorna 'agora' para check feito ha menos de 1 minuto (string naive)", () => {
      const ts = utcMinutesAgo(0)
      expect(timeAgo(ts)).toBe("agora")
    })

    it("retorna '5 min' para check feito ha 5 minutos (string naive)", () => {
      const ts = utcMinutesAgo(5)
      expect(timeAgo(ts)).toBe("5 min")
    })

    it("retorna '30 min' para check feito ha 30 minutos (string naive)", () => {
      const ts = utcMinutesAgo(30)
      expect(timeAgo(ts)).toBe("30 min")
    })

    it("retorna '2h' para check feito ha 2 horas (string naive)", () => {
      const ts = utcMinutesAgo(120)
      expect(timeAgo(ts)).toBe("2h")
    })

    it("retorna '3d' para check feito ha 3 dias (string naive)", () => {
      const ts = utcMinutesAgo(3 * 24 * 60)
      expect(timeAgo(ts)).toBe("3d")
    })

    it("funciona com string que ja tem Z", () => {
      const d = new Date(Date.now() - 45 * 60_000)
      const ts = d.toISOString()  // com Z
      expect(timeAgo(ts)).toBe("45 min")
    })

    it("funciona com string que tem offset", () => {
      // 2h atras em UTC, representado como offset -03:00 (= 5h atras local BR)
      const d = new Date(Date.now() - 2 * 60 * 60_000)
      const hours = String(d.getUTCHours()).padStart(2, "0")
      const mins = String(d.getUTCMinutes()).padStart(2, "0")
      const secs = String(d.getUTCSeconds()).padStart(2, "0")
      const ts = `${d.toISOString().slice(0, 11)}${hours}:${mins}:${secs}+00:00`
      expect(timeAgo(ts)).toBe("2h")
    })

    it("funciona com objeto Date", () => {
      const d = new Date(Date.now() - 10 * 60_000)
      expect(timeAgo(d)).toBe("10 min")
    })

    it("NAO retorna 'agora' para check de 30 min atras (bug original)", () => {
      // Este eh o teste principal: antes do fix, 30 min atras retornava "agora"
      // porque o browser adicionava +3h (BR timezone) ao interpretar a string naive
      const ts = utcMinutesAgo(30)
      const result = timeAgo(ts)
      expect(result).not.toBe("agora")
      expect(result).toBe("30 min")
    })
  })

  // =============================================
  // timeUntil — "Proximo Check"
  // =============================================
  describe("timeUntil", () => {
    it("retorna 'agora' para horario ja passado (string naive)", () => {
      const ts = utcMinutesAgo(5)
      expect(timeUntil(ts)).toBe("agora")
    })

    it("retorna 'em 15 min' para check daqui 15 minutos (string naive)", () => {
      const ts = utcMinutesFromNow(15)
      expect(timeUntil(ts)).toBe("em 15 min")
    })

    it("retorna 'em 1h' para check daqui 1 hora (string naive)", () => {
      const ts = utcMinutesFromNow(60)
      expect(timeUntil(ts)).toBe("em 1h")
    })

    it("retorna 'em 2d' para check daqui 2 dias (string naive)", () => {
      const ts = utcMinutesFromNow(2 * 24 * 60)
      expect(timeUntil(ts)).toBe("em 2d")
    })

    it("NAO retorna 'agora' para check daqui 30 min (bug original)", () => {
      const ts = utcMinutesFromNow(30)
      const result = timeUntil(ts)
      expect(result).not.toBe("agora")
      expect(result).toBe("em 30 min")
    })
  })

  // =============================================
  // formatDate / formatDateTime
  // =============================================
  describe("formatDate", () => {
    it("formata string naive corretamente", () => {
      const result = formatDate("2026-03-02T14:30:00")
      // Deve interpretar como UTC, formatado em pt-BR
      expect(result).toMatch(/\d{2}\/\d{2}\/\d{4}/)
    })

    it("formata string com Z corretamente", () => {
      const result = formatDate("2026-03-02T14:30:00Z")
      expect(result).toMatch(/\d{2}\/\d{2}\/\d{4}/)
    })

    it("formata objeto Date corretamente", () => {
      const result = formatDate(new Date("2026-03-02T14:30:00Z"))
      expect(result).toMatch(/\d{2}\/\d{2}\/\d{4}/)
    })
  })

  describe("formatDateTime", () => {
    it("formata string naive corretamente", () => {
      const result = formatDateTime("2026-03-02T14:30:00")
      // Deve conter dia/mes e hora:minuto
      expect(result).toMatch(/\d{2}\/\d{2}/)
    })

    it("formata string com Z corretamente", () => {
      const result = formatDateTime("2026-03-02T14:30:00Z")
      expect(result).toMatch(/\d{2}\/\d{2}/)
    })
  })

  // =============================================
  // Consistencia: naive vs Z devem produzir o mesmo resultado
  // =============================================
  describe("consistencia naive vs Z", () => {
    it("timeAgo retorna o mesmo resultado para naive e Z", () => {
      const naive = utcMinutesAgo(45)
      const withZ = naive + "Z"
      expect(timeAgo(naive)).toBe(timeAgo(withZ))
    })

    it("timeUntil retorna o mesmo resultado para naive e Z", () => {
      const naive = utcMinutesFromNow(45)
      const withZ = naive + "Z"
      expect(timeUntil(naive)).toBe(timeUntil(withZ))
    })

    it("formatDate retorna o mesmo resultado para naive e Z", () => {
      const naive = "2026-06-15T10:00:00"
      const withZ = "2026-06-15T10:00:00Z"
      expect(formatDate(naive)).toBe(formatDate(withZ))
    })

    it("formatDateTime retorna o mesmo resultado para naive e Z", () => {
      const naive = "2026-06-15T10:00:00"
      const withZ = "2026-06-15T10:00:00Z"
      expect(formatDateTime(naive)).toBe(formatDateTime(withZ))
    })
  })
})
