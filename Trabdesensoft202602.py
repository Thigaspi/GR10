import tkinter as tk
from tkinter import filedialog, messagebox
import pygame
import pygame.midi
import re
import threading
import time
from midiutil import MIDIFile

class EventoMusical:
    def __init__(self, pitch, start_beat, duration_beats, volume, instrument):
        self.pitch = pitch
        self.start_beat = start_beat
        self.duration_beats = duration_beats
        self.volume = volume
        self.instrument = instrument

class AnalisadorTexto:
    DURACOES = {'1': 4.0, '2': 2.0, '3': 1.0, '4': 0.5, '5': 0.25, '6': 0.125, '7': 0.0625}
    NOTAS_BASE = {'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11}
    
    def __init__(self):
        self.bpm_global = 120

    def parse(self, texto):
        linhas = texto.split('\n')
        eventos_totais = []
        self.bpm_global = 120
        
        oitavas_base = [6, 5, 4, 3]
        volumes_base = [100, 80, 60, 40]
        instrumentos_base = [6, 20, 0, 70]
        
        for idx, linha in enumerate(linhas):
            if not linha.strip(): continue
            
            voz_idx = idx % 4 
            oitava_default = oitavas_base[voz_idx]
            oitava = oitava_default
            volume = volumes_base[voz_idx]
            instrumento = instrumentos_base[voz_idx]
            
            beat_atual = 0.0
            ultima_nota_pitch = None
            
            match_delay = re.match(r'^\[(\d+)\]\s*', linha)
            if match_delay:
                beat_atual += float(match_delay.group(1))
                linha = linha[match_delay.end():]

            i = 0
            while i < len(linha):
                char = linha[i]
                duracao_atual = 1.0
                
                if char in self.NOTAS_BASE:
                    pitch = self.NOTAS_BASE[char] + (oitava + 1) * 12
                    
                    if i + 1 < len(linha) and linha[i+1] in ['#', 'b']:
                        i += 1
                        pitch += 1 if linha[i] == '#' else -1
                        
                    if i + 2 < len(linha) and linha[i+1] == ':' and linha[i+2] in self.DURACOES:
                        duracao_atual = self.DURACOES[linha[i+2]]
                        i += 2
                        
                    eventos_totais.append(EventoMusical(pitch, beat_atual, duracao_atual, volume, instrumento))
                    ultima_nota_pitch = pitch
                    beat_atual += duracao_atual
                
                elif char == ' ': volume = min(127, volume * 2)
                elif char == '!': instrumento = 24
                elif char in 'OoIiUu': instrumento = 110
                elif char == ';': instrumento = 15
                elif char == ',': instrumento = 114
                elif char == '?':
                    oitava += 1
                    if oitava > 9: oitava = oitava_default
                elif char == 'V':
                    oitava = max(0, oitava - 1)
                elif char == '>': self.bpm_global += 10
                elif char == '<': self.bpm_global = max(10, self.bpm_global - 10)
                elif char.isdigit() and (i == 0 or linha[i-1] != ':'):
                    digito = int(char)
                    if digito % 2 == 0: instrumento = (instrumento + digito) % 128
                    else: instrumento = 15
                elif char in 'abcdefg':
                    beat_atual += duracao_atual
                    ultima_nota_pitch = None
                elif char.isalpha():
                    if ultima_nota_pitch is not None:
                        eventos_totais.append(EventoMusical(ultima_nota_pitch, beat_atual, duracao_atual, volume, instrumento))
                    beat_atual += duracao_atual
                    
                i += 1
                
        return eventos_totais, self.bpm_global

class MotorAudioPygame:
    def __init__(self):
        pygame.init()
        pygame.midi.init()
        self.midi_out = None
        self.is_playing = False
        
        port_id = pygame.midi.get_default_output_id()
        if port_id != -1:
            try:
                self.midi_out = pygame.midi.Output(port_id)
            except Exception as e:
                print(f"Erro ao inicializar MIDI: {e}")

    def tocar(self, eventos, bpm, reverso=False):
        if not self.midi_out or not eventos: return
        self.is_playing = True
        
        if reverso:
            tempo_total = max(e.start_beat + e.duration_beats for e in eventos)
            eventos_proc = []
            for e in eventos:
                novo_start = tempo_total - (e.start_beat + e.duration_beats)
                eventos_proc.append(EventoMusical(e.pitch, novo_start, e.duration_beats, e.volume, e.instrument))
            eventos_proc.sort(key=lambda x: x.start_beat)
        else:
            eventos_proc = sorted(eventos, key=lambda x: x.start_beat)

        segundos_por_beat = 60.0 / bpm
        tempo_inicial = time.time()
        
        for evento in eventos_proc:
            if not self.is_playing: break
            
            tempo_alvo = tempo_inicial + (evento.start_beat * segundos_por_beat)
            while time.time() < tempo_alvo:
                if not self.is_playing: return
                time.sleep(0.005)
                
            self.midi_out.set_instrument(evento.instrument)
            self.midi_out.note_on(evento.pitch, evento.volume)
            
            t = threading.Timer(evento.duration_beats * segundos_por_beat, 
                                lambda p=evento.pitch: self.midi_out.note_off(p, 0))
            t.start()

    def parar(self):
        self.is_playing = False
        if self.midi_out:
            for pitch in range(128):
                self.midi_out.note_off(pitch, 0)

class ExportadorMIDI:
    @staticmethod
    def salvar(eventos, bpm, caminho):
        midi = MIDIFile(1)
        midi.addTempo(0, 0, bpm)
        for e in eventos:
            midi.addProgramChange(0, 0, 0, e.instrument)
            midi.addNote(0, 0, e.pitch, e.start_beat, e.duration_beats, e.volume)
        with open(caminho, "wb") as output_file:
            midi.writeFile(output_file)

class InterfaceGrafica:
    def __init__(self, root):
        self.root = root
        self.root.title("Gerador de Música (Polifonia - 4 Vozes)")
        self.parser = AnalisadorTexto()
        self.audio = MotorAudioPygame()
        
        tk.Label(root, text="Cada linha é uma voz (V0 a V3). Sintaxe: Nota[#|b]:Duração (ex: A#:3, C:1)").pack(pady=5)
        
        self.text_area = tk.Text(root, height=8, width=80)
        self.text_area.pack(pady=5)
        texto_exemplo = "[0] C:2 D:2 E:1\n[2] A:3 B:3 C:2\n[4] F:4 G:4 A:2 > >\n[6] C:3 C:3 C:3"
        self.text_area.insert(tk.END, texto_exemplo) 
        
        btn_frame = tk.Frame(root)
        btn_frame.pack(pady=5)
        
        tk.Button(btn_frame, text="Carregar TXT", command=self.carregar_txt).grid(row=0, column=0, padx=5)
        tk.Button(btn_frame, text="Salvar TXT", command=self.salvar_txt).grid(row=0, column=1, padx=5)
        tk.Button(btn_frame, text="▶ Tocar", bg="lightgreen", command=lambda: self.iniciar_reproducao(False)).grid(row=0, column=2, padx=5)
        tk.Button(btn_frame, text="◀ Tocar Reverso", bg="lightblue", command=lambda: self.iniciar_reproducao(True)).grid(row=0, column=3, padx=5)
        tk.Button(btn_frame, text="■ Parar", bg="salmon", command=self.audio.parar).grid(row=0, column=4, padx=5)
        tk.Button(btn_frame, text="Exportar MIDI", command=self.exportar_midi).grid(row=0, column=5, padx=5)
        
        # Frame contendo o Canvas e a barra de rolagem horizontal
        frame_canvas = tk.Frame(root)
        frame_canvas.pack(pady=10, fill=tk.BOTH, expand=True)
        
        self.canvas = tk.Canvas(frame_canvas, height=350, width=700, bg="#2b2b2b", relief="sunken", borderwidth=2)
        self.scroll_x = tk.Scrollbar(frame_canvas, orient=tk.HORIZONTAL, command=self.canvas.xview)
        self.canvas.configure(xscrollcommand=self.scroll_x.set)
        
        self.canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self.scroll_x.pack(side=tk.BOTTOM, fill=tk.X)
        
        self.desenhar_linhas_partitura_base()

    def carregar_txt(self):
        caminho = filedialog.askopenfilename(filetypes=[("Text Files", "*.txt")])
        if caminho:
            with open(caminho, 'r', encoding='utf-8') as f:
                self.text_area.delete(1.0, tk.END)
                self.text_area.insert(tk.END, f.read())

    def salvar_txt(self):
        caminho = filedialog.asksaveasfilename(defaultextension=".txt")
        if caminho:
            with open(caminho, 'w', encoding='utf-8') as f:
                f.write(self.text_area.get(1.0, tk.END))

    def desenhar_linhas_partitura_base(self, largura_total=700):
        self.canvas.delete("all")
        centro_y = 175
        distancia_semitom = 4
        
        # Desenha as 5 linhas da Clave de Sol (E4 a F5)
        linhas_sol = [64, 67, 71, 74, 77]
        for pitch in linhas_sol:
            y = centro_y - (pitch - 60) * distancia_semitom
            self.canvas.create_line(0, y, largura_total, y, fill="#555")
            
        # Desenha as 5 linhas da Clave de Fá (G2 a A3)
        linhas_fa = [43, 47, 50, 53, 57]
        for pitch in linhas_fa:
            y = centro_y - (pitch - 60) * distancia_semitom
            self.canvas.create_line(0, y, largura_total, y, fill="#555")

        # Dó Central (C4 - Pitch 60) tracejado para referência visual
        y_do_central = centro_y
        self.canvas.create_line(0, y_do_central, largura_total, y_do_central, fill="#888", dash=(4, 4))

    def atualizar_partitura(self, eventos):
        if not eventos: return
        
        max_beats = max(e.start_beat + e.duration_beats for e in eventos)
        pixels_por_beat = 60 # Espaçamento fixo horizontal, a partitura crescerá conforme necessário
        largura_total = max(700, int(max_beats * pixels_por_beat) + 100)
        
        self.canvas.config(scrollregion=(0, 0, largura_total, 350))
        self.desenhar_linhas_partitura_base(largura_total)
        
        centro_y = 175
        distancia_semitom = 4
        cores_vozes = ["#4da6ff", "#5cd65c", "#ff6666", "#d279d2"]
        
        for e in eventos:
            x1 = 20 + (e.start_beat * pixels_por_beat)
            x2 = 20 + ((e.start_beat + e.duration_beats) * pixels_por_beat) - 2 # -2 para espaçamento visual entre notas coladas
            y = centro_y - (e.pitch - 60) * distancia_semitom
            
            cor_idx = [6, 20, 0, 70].index(e.instrument) if e.instrument in [6, 20, 0, 70] else 0
            
            # Desenha a nota como um bloco, mapeando a altura real
            self.canvas.create_rectangle(x1, y-3, x2, y+3, fill=cores_vozes[cor_idx], outline="black")

    def iniciar_reproducao(self, reverso):
        self.audio.parar()
        texto = self.text_area.get(1.0, tk.END)
        eventos, bpm = self.parser.parse(texto)
        
        if eventos:
            self.atualizar_partitura(eventos)
            threading.Thread(target=self.audio.tocar, args=(eventos, bpm, reverso), daemon=True).start()
        else:
            messagebox.showinfo("Aviso", "O texto não gerou nenhuma nota musical válida.")

    def exportar_midi(self):
        texto = self.text_area.get(1.0, tk.END)
        eventos, bpm = self.parser.parse(texto)
        if eventos:
            caminho = filedialog.asksaveasfilename(defaultextension=".mid")
            if caminho:
                ExportadorMIDI.salvar(eventos, bpm, caminho)
                messagebox.showinfo("Sucesso", "Arquivo MIDI exportado com sucesso!")

if __name__ == "__main__":
    root = tk.Tk()
    app = InterfaceGrafica(root)
    root.mainloop()