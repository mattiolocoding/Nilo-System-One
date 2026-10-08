# SPDX-License-Identifier: Apache-2.0
"""Additional complete-request grammars. Never extract argv from these matches."""

REQUEST_PATTERNS = {
    "time": (
        r"(?:tell me )?(?:what(?:'s| is) (?:the )?(?:current |local )?(?:time|date)(?: now)?|the (?:current |local )?(?:time|date))",
        r"(?:mi dici |dimmi )?che (?:ora|ore) (?:[eè]|sono)(?: adesso)?",
        r"quelle (?:heure|date) est[- ](?:il|on)(?: aujourd'hui)?",
        r"¿?qu[eé] hora es",
        r"wie sp[aä]t ist es",
    ),
    "list_files": (
        r"(?:list|show|display) (?:the )?(?:contents|files)(?: (?:of|in) (?:this|the current) (?:directory|folder))",
        r"(?:mostra(?:mi)?|fammi vedere|elenca) (?:i file|il contenuto)(?: (?:nella|della) cartella (?:corrente|attuale))?",
        r"(?:montre|affiche|lister) (?:les fichiers|le contenu)(?: du r[eé]pertoire (?:actuel|courant))?",
        r"(?:muestra|lista) los archivos(?: de la carpeta actual)?",
        r"(?:zeige|liste) (?:die )?dateien(?: im aktuellen verzeichnis)?",
    ),
    "identity": (
        r"(?:which|what) user am i (?:logged|signed) in as",
        r"(?:what(?:'s| is)|show|tell me) (?:my|the) (?:current )?(?:user ?name|login name)",
        r"qual [eè] (?:il )?(?:mio )?nome utente(?: (?:attuale|corrente))?",
        r"(?:wie hei(?:ß|ss)t|zeige) (?:der |den )?aktuelle(?:n)? benutzer",
        r"quel est (?:le nom de )?l['’]utilisateur (?:actuel|courant)",
    ),
    "directory": (
        r"(?:print|show|display|what is) (?:my|the) (?:current )?working directory",
        r"(?:mostra(?:mi)?|dimmi) (?:il )?percorso della (?:directory|cartella) (?:corrente|attuale)",
        r"quel est le r[eé]pertoire de travail (?:actuel|courant)",
        r"¿?cu[aá]l es (?:el directorio|la carpeta) actual",
        r"(?:zeige das|was ist das) aktuelle (?:arbeits)?verzeichnis",
    ),
    "hostname": (
        r"what (?:is (?:this|the) (?:computer|machine) called|is (?:this|the) (?:computer|machine)(?:'s)? name)",
        r"come si chiama (?:questo|il) (?:computer|host)",
        r"¿?cu[aá]l es el nombre de (?:este|el) (?:equipo|ordenador)",
        r"quel est le nom de (?:cet ordinateur|cette machine)",
        r"wie hei(?:ß|ss)t (?:dieser|der) computer",
    ),
    "system": (
        r"(?:which|what) operating system (?:is running|am i using|is this)",
        r"quale sistema operativo (?:[eè] in uso|sto usando|[eè] installato)",
        r"welches betriebssystem l[aä]uft(?: hier)?",
        r"quel syst[eè]me d['’]exploitation (?:est utilis[eé]|est install[eé])",
        r"¿?qu[eé] sistema operativo (?:estoy usando|est[aá] instalado)",
    ),
    "uptime": (
        r"how long has (?:this|the) (?:system|computer|machine) been (?:up|running|on)",
        r"depuis combien de temps (?:cet ordinateur|ce syst[eè]me) (?:fonctionne|est allum[eé])(?:[- ]t[- ]il)?",
        r"¿?cu[aá]nto tiempo lleva encendido (?:el|este) (?:equipo|ordenador)",
        r"wie lange l[aä]uft (?:dieser|der) computer",
    ),
    "disk": (
        r"how much (?:free |available )?disk space (?:is (?:left|available|free)|do i have)",
        r"quanto spazio (?:libero |disponibile )?(?:rimane|ho|c['’][eè]) sul disco",
        r"¿?cu[aá]nto espacio libre queda en el disco",
        r"combien d['’]espace disque (?:est libre|reste[- ]t[- ]il)",
        r"wie viel (?:speicherplatz|platz) ist auf (?:der festplatte|dem datentr[aä]ger) frei",
    ),
    "memory": (
        r"how much (?:ram|memory) (?:is (?:available|free)|do i have available)",
        r"quanta (?:memoria(?: ram)?|ram) (?:libera ho|[eè] (?:libera|disponibile))",
        r"wie viel (?:arbeitsspeicher|ram) ist (?:frei|verf[uü]gbar)",
        r"combien de (?:ram|m[eé]moire) est disponible",
        r"¿?cu[aá]nta (?:memoria|ram) (?:libre hay|est[aá] disponible)",
    ),
}
