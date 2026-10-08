# Nilo

**Nilo** è il nome dell'agente di `internal-jev`: un router locale che risolve
richieste semplici con tool CLI (System 1) e può inviare le altre a un modello
locale tramite Ollama (System 2). Le risposte sono JSON e includono `agent: "Nilo"`.
Il progetto nasce come esperimento di routing ispirato a Jev e ai sistemi con
due livelli di elaborazione.

Richiede **Python 3.10+** e i comandi Linux elencati sotto. Usa solo la libreria
standard Python; per System 2 occorrono Ollama attivo e un modello già scaricato.

Licenza: [Apache-2.0](LICENSE).

## Avvio

```bash
git clone https://github.com/mattiolocoding/Nilo-System-One.git
cd Nilo-System-One
python3 internal_jev.py "che ora è?"
python3 internal_jev.py "spazio su disco"
python3 internal_jev.py --help
```

I nomi `internal_jev.py` e `test_internal_jev.py` rimangono compatibili con gli
import e i comandi precedenti.

## Intenti System 1

| Intento | Esempi italiani / inglesi | Comando fisso |
| --- | --- | --- |
| Ora e data | `che ora è?`, `what time is it?`, `date` | `date` |
| File della cartella corrente | `lista file`, `list files`, `ls` | `ls -la` |
| Utente corrente | `chi sono`, `who am i`, `whoami` | `whoami` |
| Cartella corrente | `dove mi trovo?`, `current directory`, `pwd` | `pwd` |
| Nome del computer | `nome del computer`, `hostname` | `hostname` |
| Sistema operativo | `sistema operativo`, `system information` | `uname -srm` |
| Tempo di attività | `tempo di attività`, `uptime` | `uptime` |
| Spazio disco | `spazio su disco`, `disk space` | `df -h` |
| Memoria | `memoria disponibile`, `memory usage` | `free -h` |

Sono accettate maiuscole, spazi ripetuti, punteggiatura finale e alcune formule
di cortesia (`puoi darmi la lista file please`, `please show files`). Il matching
copre l'intera richiesta: `tell me a joke about time`, `explain ls`, richieste
con più intenti e comandi con argomenti arbitrari vanno a System 2.

Per aggiungere un intento, aggiungere una voce a `TOOL_INTENTS` con regex e
comando fisso, quindi verificare esempi positivi e richieste ambigue nei test.

## Decisioni prima dell'esecuzione

Ispirandosi al modello di decisioni tipizzate di
[Rizzo Flow](https://github.com/Rizzo-AI-Academy/rizzo-flow), Nilo separa la
decisione dall'esecuzione. `decide_query()` restituisce una `RoutingDecision`
immutabile con azione, motivo, intento e comando consentito. Non esegue tool
e non chiama un modello. `route_query()` applica questa decisione.

```bash
python3 internal_jev.py --decide-only "lista file"
python3 internal_jev.py --decide-only "Spiega come funziona ls"
```

La modalità `--decide-only` restituisce `status: "decision"` e costa zero token.
Ogni risposta include `routing.method`, `routing.action` e `routing.reason`,
così la scelta è ispezionabile anche quando manca un modello o un tool fallisce.
Il routing attuale usa regex deterministiche e non produce probabilità o logits.

Rizzo Flow è il riferimento per decisioni strutturate, astensione e misure
esplicite. Nilo mantiene un'implementazione indipendente con la sola libreria
standard; nessun codice o peso del progetto di riferimento è incorporato.
Revisione consultata: `b9ba007ee4d2928bbab5b1d8bfe9009c3696b6de`.

## System 2 locale

Attivare il fallback con il nome di un modello installato:

```bash
ollama list
python3 internal_jev.py --model qwen2.5:7b-instruct "Spiega la gravità in una frase."
```

Oppure impostare il modello per le successive invocazioni della CLI:

```bash
export INTERNAL_JEV_MODEL=qwen2.5:7b-instruct
python3 internal_jev.py "Scrivi una breve poesia sul mare."
python3 internal_jev.py --no-system-2 "Scrivi una breve poesia sul mare."
```

`--model` prevale sulla variabile d'ambiente. `--no-system-2` disabilita sempre
il fallback. Senza modello, una richiesta complessa restituisce
`status: "routed_to_system_2"` e indica come configurarlo; nessuna inferenza viene
eseguita. Le richieste riconosciute da System 1 non chiamano l'LLM anche quando
è configurato.

Il server predefinito è `http://127.0.0.1:11434`. Si può cambiarlo con
`--ollama-url` o `INTERNAL_JEV_OLLAMA_URL`, usando esclusivamente un'origine
HTTP(S) su loopback (`localhost`, `127.0.0.1`, `::1`). Proxy d'ambiente e redirect
HTTP sono disabilitati. Scegliere un modello locale, non un modello cloud.
Il client usa [`POST /api/generate`](https://docs.ollama.com/api/generate) con
`stream: false` e un prompt di sistema che presenta Nilo e richiede risposte
brevi nella lingua dell'utente.

Limiti configurabili:

- `--tool-timeout`: attesa del comando CLI, default 5 secondi.
- `--llm-timeout`: timeout di attesa delle operazioni HTTP, default 60 secondi.
- `--max-tokens`: limite dei token generati da Ollama, default 256.

Il timeout HTTP non garantisce la cancellazione dell'inferenza sul server.
La risposta HTTP accettata è limitata a 1 MiB. Il timeout comprende anche
l'eventuale attesa per il caricamento del modello.

Uso da Python (la configurazione è esplicita; le variabili d'ambiente sono lette
dalla CLI):

```python
from internal_jev import OllamaConfig, route_query

config = OllamaConfig(model="qwen2.5:7b-instruct", timeout=60, max_tokens=128)
result = route_query("Spiega la gravità in una frase.", system_2=config)
```

## Output e metriche

- `system`: 1 per un tool CLI, 2 per il fallback.
- `execution_time_ms`: tempo misurato con `time.perf_counter()`, incluse attese
  ed errori; non è una stima.
- `cost_tokens`: 0 per System 1 e per il fallback disabilitato; per System 2 è
  la somma dei token di input e output restituiti da Ollama, riportati anche
  in `usage`. È un conteggio di token, non un costo monetario.
- `cost_tokens: null`: consumo sconosciuto quando Ollama non riporta metriche
  valide o la richiesta fallisce. Non viene dichiarato falsamente zero.
- `status: "success"`: comando terminato con successo o generazione conclusa
  con testo. `done_reason: "length"`, quando presente, indica che il modello
  ha raggiunto il limite di generazione.
- `status: "error"`: timeout, comando mancante/fallito, server indisponibile,
  errore HTTP o risposta invalida/incompleta. La CLI termina con codice 1.
  Una richiesta complessa senza modello ha codice 0 ma resta esplicitamente
  `routed_to_system_2`, senza risposta generata.

I contatori seguono la [documentazione delle metriche Ollama](https://docs.ollama.com/api/usage).
I tempi dipendono dal computer, dal modello e dal suo stato di caricamento;
il progetto non dichiara rapporti di velocità o risparmio non misurati.

## Sicurezza e verifiche

I tool sono una allowlist di comandi e argomenti fissi, di sola lettura.
`subprocess.run` riceve argv separati, `shell=False` e un timeout. Percorsi,
opzioni e metacaratteri forniti nella query non vengono aggiunti al comando.
Il testo restituito dal modello viene mostrato e non eseguito.

```bash
python3 -m unittest test_internal_jev.py -v
```

La suite conserva gli smoke test originali e copre nuovi intenti, injection,
richieste ambigue, timeout, errori CLI, configurazione e contabilità token.
I test HTTP usano un server temporaneo su loopback: non richiedono Ollama,
download di modelli o accesso a servizi esterni. I comandi Linux devono essere
disponibili per gli smoke test System 1.

GitHub Actions esegue la stessa suite su Ubuntu con Python 3.10, 3.12 e 3.14.
