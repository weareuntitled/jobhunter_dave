# Bullet-Pool statt Live-Generierung für CV-Inhalte

**Entscheidung:** CV-Bullet-Points werden aus einem festen, manuell kuratierten Pool (43 Bullets, 6 Kategorien) per Keyword-Matching selektiert – nicht live von der Go-API generiert.

**Warum:** Daniel Peters' Stärke liegt in präzisen, messbaren Formulierungen aus seiner realen Berufserfahrung. Live-generierte Bullets riskieren Ungenauigkeiten oder erfundene Metriken. Ein fester Pool garantiert, dass jeder Bullet faktisch korrekt ist und seinem authentischen Sprachstil entspricht. Die Go-API übernimmt nur die Selektion und Reihenfolge, nicht die Textgenerierung.

**Status:** accepted

**Considered Options:**
- *Live-Generierung via Go-API*: Flexibler, aber riskant – generierte Metriken könnten erfunden sein, Formulierungen könnten vom authentischen Stil abweichen.
- *Hybrid: Pool + leichte Adaption*: Agent hätte Bullets umformulieren dürfen. Verworfen weil die Original-Formulierungen bereits optimiert sind.
