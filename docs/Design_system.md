## Design system

### Token file: lib/theme/tokens.dart (Flutter equivalent of the :root block)
All values live here. Never hardcode a color, radius, or spacing value elsewhere.

### Brand colors
--knit-accent:        #c4622d   (primary CTA, active states, score pills)
--knit-accent-light:  #e8956a   (icebreaker border)
--knit-accent-bg:     #fdf1eb   (icebreaker bg, selected tag bg)
--knit-met:           #2d6a4f   (met state)
--knit-met-bg:        #eaf4ee   (met pill bg)
--knit-live:          #1a6e3c   (live event badge)
--knit-live-bg:       #e2f4ea   (live badge bg)

### Neutral surfaces
--knit-bg:       #faf8f4   (app background)
--knit-surface:  #f4f0e8   (agenda strip, inner surfaces)
--knit-card:     #ffffff   (raised cards)
--knit-border:   #e8e2d8   (default)
--knit-border-2: #d4ccc0   (emphasis/interactive)

### Text
--knit-ink:   #1a1714   (primary)
--knit-ink-2: #5a5550   (secondary)
--knit-ink-3: #9a948e   (muted, labels)

### Typography: Georgia serif throughout
### Radii: 8 / 12 / 14 / 20px / full
### Standard padding: 20px horizontal

### Attendee nav (global, bottom): Events · Connections · Profile
### Event view nav: back arrow only — event is a drill-down from Events list
### Agenda: event-scoped, shown as surface strip inside event view + in join preview