"""Desktop console for enrollment, recognition and manual rover driving."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import ctypes
from pathlib import Path
from threading import Event, Lock, Thread
import time
import tkinter as tk
import sys
from tkinter import filedialog, messagebox, ttk

import cv2
from PIL import Image, ImageTk
from alert_people import load_watch_names, save_watch_names
from face_recognition_demo import FaceEngine, identify, read_gallery, read_profiles, remove_person, save_person
from photo_enrollment import review_photos, validate_profile
from phone_remote import PhoneRemote, lan_address
from recognition_policy import MATCH_MODES, StableRecognizer
from rover_control import RoverControl
from rtsp_source import RTSPCamera, load_settings, save_settings
from telegram_alerts import MatchGate, TelegramAlerts, load_alert_settings

ROOT = Path(__file__).resolve().parent


class Monitor:
    def __init__(self, settings, gallery, watch, telegram, preview, mode='Balanced'):
        self.stop = Event()
        self.lock = Lock()
        self.latest = None, 'Starting camera…', (), 0
        self.metrics = {}
        self.thread = Thread(target=self.run, args=(settings, gallery, watch, telegram, preview, mode), daemon=True)
        self.thread.start()

    def publish(self, frame, status, names=(), retrieved=0):
        with self.lock:
            self.latest = frame, status, names, retrieved

    def run(self, settings, gallery, watch, telegram, preview, mode):
        camera = None
        alerts = None
        try:
            self.publish(None, 'Loading face models… First setup may download 14 MB.' if not preview else 'Connecting camera…')
            engine = None if preview else FaceEngine(mode)
            if self.stop.is_set():
                return
            alerts = TelegramAlerts(telegram) if telegram and watch and engine else None
            gate = MatchGate()
            stable = StableRecognizer()
            camera = RTSPCamera(settings)
            last, generation = -1, -1
            while not self.stop.wait(0.02):
                if camera.failure:
                    self.publish(None, camera.failure)
                    return
                item = camera.get()
                if item is None or generation != camera.generation:
                    gate.reset()
                    stable.reset()
                    generation = camera.generation
                if item is None:
                    self.publish(None, f'Camera: {camera.status}')
                    continue
                seq, frame, retrieved = item
                if seq == last:
                    continue
                last = seq
                started = time.perf_counter()
                found = (engine.identify_faces(frame, gallery) if gallery else
                         [(row, 'Unknown') for row in engine.detect(frame)]) if engine else []
                if self.stop.is_set() or generation != camera.generation or camera.get() is None or time.perf_counter() - retrieved > 2:
                    gate.reset()
                    stable.reset()
                    continue
                found = stable.update(found, gallery, retrieved)
                names = tuple(sorted({label for _, label in found if label in gallery}))
                height, width = frame.shape[:2]
                scale = min(780/width, 440/height, 1)
                view = cv2.resize(frame, (max(1, round(width*scale)), max(1, round(height*scale))))
                for row, label in found:
                    x,y,w,h = (round(float(v)*scale) for v in row[:4])
                    color = (70,205,100) if label in gallery else (40,205,245)
                    cv2.rectangle(view,(x,y),(x+w,y+h),color,2)
                    cv2.putText(view,label,(max(0,x),max(20,y-7)),cv2.FONT_HERSHEY_SIMPLEX,.6,color,2)
                if alerts:
                    gate.observe(set(names) & watch,time.monotonic(),alerts.enqueue)
                elapsed = time.perf_counter() - started
                self.metrics = {'source_width':width,'source_height':height,'analysis_ms':round(elapsed*1000,1),
                                'faces':len(found),'preview':preview,'mode':mode}
                status = 'Preview only' if preview else f'{len(found)} face(s) · {elapsed * 1000:.0f} ms / analysis · {mode}'
                if alerts:
                    status += ' · Telegram: ' + alerts.status
                self.publish(cv2.cvtColor(view,cv2.COLOR_BGR2RGB),status,names,retrieved)
        except (ValueError, RuntimeError):
            self.publish(None,'Face models could not load. Check internet on first setup and run 04_CHECK_SETUP.')
        except Exception:
            self.publish(None,'Camera or model startup failed. Check the camera settings and run 04_CHECK_SETUP.')
        finally:
            if alerts:
                alerts.close()
            if camera:
                camera.close()


class App:
    def __init__(self, root, preview=False):
        self.root = root
        self.monitor = self.rover = self.held = self.picture = self.last_frame = self.job = None
        self.phone_remote = None
        self.direction_buttons = []
        self.paths = ()
        self.review = None
        self.photo_engine = None
        self.job_done = None
        self.pool = ThreadPoolExecutor(max_workers=1)
        self.name,self.person_id,self.role,self.address = (tk.StringVar() for _ in range(4))
        self.mark,self.notify = tk.BooleanVar(),tk.BooleanVar()
        self.mode = tk.StringVar(value='Balanced')
        self.enrollment_mode = tk.StringVar(value='Add photos')
        self.preview = tk.BooleanVar(value=preview)
        self.form = tk.StringVar(value='Enter a name, then choose 3–5 clear photos. Photos are checked before saving.')
        self.profile_info = tk.StringVar(value='No profiles yet')
        self.camera_status = tk.StringVar(value='Camera stopped')
        self.rover_status = tk.StringVar(value='Disconnected')
        self.matches = tk.StringVar(value='No live matches')
        self.phone_info = tk.StringVar(value='Off. Start sharing to show the address and pairing code.')
        root.title('Neural Rover | Face Recognition')
        root.geometry('1130x680')
        root.minsize(900,620)
        ttk.Style(root).configure('Title.TLabel',font=('Segoe UI',23,'bold'))
        shell = ttk.Frame(root,padding=12)
        shell.pack(fill='both',expand=True)
        ttk.Label(shell,text='Neural Rover',style='Title.TLabel').pack(anchor='w')
        ttk.Label(shell,text='1  Add a person     2  Choose and check photos     3  Save     4  Start camera').pack(anchor='w',pady=(0,10))
        tabs = ttk.Notebook(shell,width=325)
        people_page = ttk.Frame(tabs)
        self.people_canvas = tk.Canvas(people_page,highlightthickness=0,width=305)
        people_scroll = ttk.Scrollbar(people_page,orient='vertical',command=self.people_canvas.yview)
        self.people_canvas.configure(yscrollcommand=people_scroll.set)
        people_scroll.pack(side='right',fill='y')
        self.people_canvas.pack(side='left',fill='both',expand=True)
        side = ttk.Frame(self.people_canvas,padding=4)
        self.people_content = side
        self.people_window = self.people_canvas.create_window((0,0),window=side,anchor='nw')
        side.bind('<Configure>',lambda _event:self.people_canvas.configure(scrollregion=self.people_canvas.bbox('all')))
        self.people_canvas.bind('<Configure>',lambda event:self.people_canvas.itemconfigure(self.people_window,width=event.width))
        root.bind_all('<MouseWheel>',self.scroll_people,add='+')
        drive = ttk.Frame(tabs,padding=4)
        phone = ttk.Frame(tabs,padding=8)
        tabs.add(people_page,text='People')
        tabs.add(drive,text='Rover controls')
        tabs.add(phone,text='Phone remote')
        tabs.pack(side='left',fill='y',padx=(0,12))
        video = ttk.Frame(shell)
        video.pack(side='left',fill='both',expand=True)
        enroll = ttk.LabelFrame(side,text='Add or improve a person',padding=8)
        enroll.pack(fill='x')
        for title,var in [('Name',self.name),('ID (optional)',self.person_id),('Role (optional)',self.role)]:
            ttk.Label(enroll,text=title).pack(anchor='w')
            ttk.Entry(enroll,textvariable=var,width=30).pack(fill='x',pady=(0,4))
        ttk.Combobox(enroll,textvariable=self.enrollment_mode,values=('Add photos','Replace photos'),state='readonly',width=28).pack(fill='x',pady=3)
        ttk.Button(enroll,text='Choose & check photos…',command=self.choose).pack(fill='x')
        ttk.Checkbutton(enroll,text='Notify me for this person',variable=self.mark).pack(anchor='w')
        ttk.Button(enroll,text='Save person',command=self.enroll).pack(fill='x')
        ttk.Label(enroll,textvariable=self.form,wraplength=280).pack(anchor='w',pady=5)
        review_box = ttk.Frame(enroll)
        review_box.pack(fill='x')
        self.review_text = tk.Text(review_box,height=4,width=30,wrap='word',state='disabled',font=('Segoe UI',9))
        review_scroll = ttk.Scrollbar(review_box,orient='vertical',command=self.review_text.yview)
        self.review_text.configure(yscrollcommand=review_scroll.set)
        review_scroll.pack(side='right',fill='y')
        self.review_text.pack(side='left',fill='both',expand=True)
        profiles = ttk.LabelFrame(side,text='Saved profiles',padding=8)
        profiles.pack(fill='x',pady=7)
        self.people = tk.Listbox(profiles,height=4,exportselection=False)
        self.people.pack(fill='x')
        self.people.bind('<<ListboxSelect>>',self.select_profile)
        ttk.Label(profiles,textvariable=self.profile_info,wraplength=275).pack(anchor='w')
        ttk.Button(profiles,text='Save alert choice',command=self.save_mark).pack(side='left',pady=4)
        ttk.Button(profiles,text='Remove',command=self.remove).pack(side='right')
        actions = ttk.Frame(side)
        actions.pack(fill='x',pady=4)
        ttk.Button(actions,text='New person',command=self.new_person).pack(side='left')
        ttk.Button(actions,text='Test a photo…',command=self.test_photo).pack(side='right')
        ttk.Label(side,text='Add varied photos to improve a saved profile. Use a different photo for testing.',wraplength=290).pack(anchor='w',pady=4)
        controls = ttk.LabelFrame(drive,text='Rover · hold to drive',padding=8)
        controls.pack(fill='x')
        ttk.Label(controls,text='Main ESP32 IP address (not the Tapo IP)').grid(row=0,column=0,columnspan=3,sticky='w')
        ttk.Entry(controls,textvariable=self.address,width=18).grid(row=1,column=0,columnspan=2,sticky='ew')
        ttk.Button(controls,text='Connect',command=self.connect_rover).grid(row=1,column=2)
        ttk.Label(controls,textvariable=self.rover_status,wraplength=275).grid(row=2,column=0,columnspan=3,sticky='w')
        for title,direction,row,col in [('Forward','F',2,1),('Left','L',3,0),('Right','R',3,2),('Reverse','B',4,1)]:
            button = ttk.Button(controls,text=title,width=8)
            self.direction_buttons.append(button)
            button.grid(row=row+1,column=col,padx=2,pady=2)
            button.bind('<ButtonPress-1>',lambda event, code=direction:self.press(event.widget,code))
            button.bind('<Leave>',lambda _event:self.stop_rover())
        ttk.Button(controls,text='STOP',width=8,command=self.stop_rover).grid(row=4,column=1)
        ttk.Button(controls,text='Disconnect rover',command=self.disconnect_rover).grid(row=6,column=0,columnspan=3,sticky='ew',pady=8)
        ttk.Label(drive,text='Test with wheels raised first.\nRelease a direction button, click STOP, or press Escape to stop.\nClose other rover control pages before connecting.',wraplength=290).pack(anchor='w',pady=8)
        root.bind_all('<ButtonRelease-1>',lambda _event:self.stop_rover() if self.held else None,add='+')
        root.bind('<FocusOut>',lambda _event:self.stop_rover() if self.held else None,add='+')
        root.bind('<Escape>',lambda _event:self.stop_rover(),add='+')
        ttk.Label(phone,text='Tapo video + driving on your phone',font=('Segoe UI',12,'bold'),wraplength=290).pack(anchor='w',pady=(0,10))
        ttk.Label(phone,text='Start the camera, then share. Open the displayed laptop address in your phone browser and enter the pairing code.',wraplength=290).pack(anchor='w')
        ttk.Button(phone,text='Start phone remote',command=self.start_phone_remote).pack(fill='x',pady=(12,4))
        ttk.Button(phone,text='Stop phone remote',command=self.stop_phone_remote).pack(fill='x')
        ttk.Label(phone,textvariable=self.phone_info,wraplength=290).pack(anchor='w',pady=12)
        ttk.Label(phone,text='Keep the laptop on and all devices on the same reachable network. Connect the ESP32 from Rover controls before driving.\n\nWhile sharing, use the phone for directions. Laptop STOP, Escape and Disconnect still work. Video and driving are independent: a failed camera stream does not disable driving.\n\nThis page is for your local network. It does not provide internet access to the rover.',wraplength=290).pack(anchor='w')
        toolbar = ttk.Frame(video)
        toolbar.pack(fill='x')
        self.start_button = ttk.Button(toolbar,text='Start camera',command=self.start_camera)
        self.start_button.grid(row=0,column=0,sticky='w')
        self.stop_button = ttk.Button(toolbar,text='Stop',command=self.stop_camera,state='disabled')
        self.stop_button.grid(row=0,column=1,padx=4)
        ttk.Button(toolbar,text='Camera setup…',command=self.configure_camera).grid(row=0,column=2,padx=4)
        ttk.Label(toolbar,text='Matching:').grid(row=1,column=0,sticky='w',pady=6)
        ttk.Combobox(toolbar,textvariable=self.mode,values=tuple(MATCH_MODES),state='readonly',width=12).grid(row=1,column=1,columnspan=2,sticky='w')
        ttk.Checkbutton(toolbar,text='Preview only',variable=self.preview).grid(row=0,column=3,sticky='w')
        ttk.Checkbutton(toolbar,text='Telegram on start',variable=self.notify).grid(row=1,column=3,sticky='w')
        self.status_label = ttk.Label(video,textvariable=self.camera_status,wraplength=650)
        self.status_label.pack(anchor='w',pady=5)
        self.video = ttk.Label(video,text='Start camera to view the live feed.',anchor='center')
        self.video.pack(fill='both',expand=True)
        self.match_label = ttk.Label(video,textvariable=self.matches,wraplength=590)
        self.match_label.pack(anchor='w',pady=6)
        self.help_label = ttk.Label(video,text='Checking… confirms a face across consecutive frames. Strict reduces uncertain matches.\nMatching changes apply on the next start. Telegram requires separate pairing.',wraplength=650)
        self.help_label.pack(anchor='w')
        video.bind('<Configure>',lambda event:[label.configure(wraplength=max(200,event.width-8))
                                              for label in (self.status_label,self.match_label,self.help_label)])
        root.protocol('WM_DELETE_WINDOW',self.close)
        self.refresh()
        self.tick()

    def refresh(self):
        try:
            gallery = read_gallery()
        except (OSError, ValueError) as error:
            gallery = {}
            self.form.set(str(error))
        self.names = sorted(gallery)
        watch = load_watch_names()
        self.people.delete(0,'end')
        for name in self.names:
            self.people.insert('end',name + (' [alerts]' if name in watch else ''))
        self.profile_info.set(f'{len(self.names)} saved person(s)')

    def scroll_people(self,event):
        widget = self.root.winfo_containing(event.x_root,event.y_root)
        if widget == self.review_text:
            return
        while widget is not None:
            if widget == self.people_canvas:
                self.people_canvas.yview_scroll(-int(event.delta/120),'units')
                return 'break'
            widget = getattr(widget,'master',None)

    def selected(self):
        indexes = self.people.curselection()
        return self.names[indexes[0]] if indexes else None

    def select_profile(self,_event=None):
        if self.job:
            return
        name = self.selected()
        if name:
            fields = read_profiles().get(name,{})
            self.name.set(name)
            self.person_id.set(fields.get('id',''))
            self.role.set(fields.get('role',''))
            self.mark.set(name in load_watch_names())
            self.paths = ()
            self.review = None
            self.enrollment_mode.set('Add photos')
            self.show_review('')
            count = len(read_gallery()[name])
            self.profile_info.set(f'{name}: {count} distinct photo template(s)')
            self.form.set('Choose more photos to improve this person, or edit details and save.')

    def show_review(self, text):
        self.review_text.configure(state='normal')
        self.review_text.delete('1.0','end')
        self.review_text.insert('1.0',text)
        self.review_text.configure(state='disabled')

    def new_person(self):
        if not self.editable():
            return
        self.people.selection_clear(0,'end')
        self.name.set('')
        self.person_id.set('')
        self.role.set('')
        self.mark.set(False)
        self.paths, self.review = (), None
        self.enrollment_mode.set('Add photos')
        self.show_review('')
        self.form.set('Enter a name, then choose 3–5 photos of the same person.')

    def engine(self):
        # Called only by the single photo worker, never shared with live inference.
        if self.photo_engine is None:
            self.photo_engine = FaceEngine()
        return self.photo_engine

    def submit(self, action, done):
        self.job_done = done
        self.job = self.pool.submit(action)

    def choose(self):
        if not self.editable():
            return
        paths = filedialog.askopenfilenames(title='Choose photos of one person',filetypes=[('Photos','*.jpg *.jpeg *.png *.webp')])
        if paths:
            self.paths = paths
            self.review = None
            self.show_review('')
            self.form.set('Checking faces and photo quality… First use may download models.')
            def done(review):
                self.review = review
                self.show_review(review.summary())
                self.form.set('Review the results, then Save person.' if review.samples else 'No usable photos. Choose clearer photos and try again.')
            self.submit(lambda:review_photos(paths,self.engine()),done)

    def test_photo(self):
        if not self.editable():
            return
        gallery = read_gallery()
        if not gallery:
            self.form.set('Save at least one person before testing a photo.')
            return
        path = filedialog.askopenfilename(title='Test a different photo (nothing saved)',filetypes=[('Photos','*.jpg *.jpeg *.png *.webp')])
        if not path:
            return
        threshold, margin = MATCH_MODES[self.mode.get()]
        def test():
            review = review_photos([path],self.engine())
            if not review.samples:
                return review.summary()
            label, score = identify(review.samples[0],gallery,threshold,margin)
            return f'Result: {label}\nSimilarity: {score:.3f} (not a probability)\n\nUse photos that were not used for enrollment. One photo cannot measure real-world accuracy.'
        self.form.set('Testing photo… No profile changes will be saved.')
        self.submit(test,lambda result:(self.form.set('Photo test finished.'),messagebox.showinfo('Photo test',result)))

    @staticmethod
    def mark_person(name, enabled):
        names = load_watch_names()
        (names.add if enabled else names.discard)(name)
        save_watch_names(names)

    def editable(self):
        if self.monitor or self.job:
            self.form.set('Stop the camera and wait for any photo import to finish.')
            return False
        return True

    def enroll(self):
        if not self.editable():
            return
        try:
            name,fields = validate_profile(self.name.get(),self.person_id.get(),self.role.get())
            gallery = read_gallery()
            name = next((key for key in gallery if key.casefold() == name.casefold()),name)
            if not self.paths and name in gallery:
                save_person(gallery,name,list(gallery[name]),fields)
                self.mark_person(name,self.mark.get())
                self.refresh()
                self.form.set(f'Details saved for {name}.')
                return
            if not self.review or not self.review.samples:
                raise ValueError('Choose and check usable photos first.')
            append = self.enrollment_mode.get() == 'Add photos'
            if name in gallery and not append and not messagebox.askyesno('Replace photos',f'Replace all saved photo templates for {name}?'):
                return
            samples,marked = list(self.review.samples),self.mark.get()
            def save():
                save_person(gallery,name,samples,fields,append=append)
                self.mark_person(name,marked)
                return f'Saved {name}: {len(read_gallery()[name])} distinct photo template(s).'
            def done(result):
                self.form.set(result)
                self.paths, self.review = (), None
                self.refresh()
            self.form.set('Saving profile…')
            self.submit(save,done)
        except (ValueError,OSError) as error:
            self.form.set(str(error))

    def save_mark(self):
        name = self.selected()
        if self.editable() and name:
            self.mark_person(name,self.mark.get())
            self.refresh()
            self.form.set(f'Alert preference saved for {name}.')

    def remove(self):
        name = self.selected()
        if self.editable() and name and messagebox.askyesno('Remove profile',f'Delete templates and details for {name}?'):
            remove_person(name)
            self.mark_person(name,False)
            self.refresh()
            self.name.set('')
            self.person_id.set('')
            self.role.set('')
            self.paths = ()
            self.review = None
            self.show_review('')
            self.form.set(f'Removed {name}.')

    def configure_camera(self):
        if not self.editable():
            self.camera_status.set('Stop the camera and finish photo processing before changing setup.')
            return
        try:
            settings = load_settings(ROOT/'camera.local.json')
        except (ValueError,OSError):
            settings = {'stream':'stream2','port':554}
        dialog = tk.Toplevel(self.root)
        dialog.title('Tapo camera setup')
        dialog.transient(self.root)
        dialog.resizable(False,False)
        content = ttk.Frame(dialog,padding=18)
        content.pack(fill='both',expand=True)
        ttk.Label(content,text='Connect your Tapo camera',font=('Segoe UI',15,'bold')).pack(anchor='w')
        ttk.Label(content,text='Use the Camera Account from the Tapo app,\nunder Advanced Settings. Keep the PC and camera on the same network.').pack(anchor='w',pady=8)
        values = {}
        for key,title in [('host','Camera IP address'),('username','Camera account username'),('password','Camera account password')]:
            ttk.Label(content,text=title).pack(anchor='w')
            values[key] = tk.StringVar(value=settings.get(key,''))
            ttk.Entry(content,textvariable=values[key],width=42,show='•' if key=='password' else '').pack(fill='x',pady=(0,6))
        stream = tk.StringVar(value='High detail (stream1)' if settings.get('stream') == 'stream1' else 'Faster preview (stream2)')
        ttk.Label(content,text='Video quality').pack(anchor='w')
        ttk.Combobox(content,textvariable=stream,values=('High detail (stream1)','Faster preview (stream2)'),state='readonly').pack(fill='x')
        ttk.Label(content,text='Try high detail if distant faces are too small.\nCredentials are saved only on this computer.').pack(anchor='w',pady=8)
        error = tk.StringVar()
        ttk.Label(content,textvariable=error,wraplength=350).pack(anchor='w')
        def save():
            try:
                save_settings(ROOT/'camera.local.json', {**settings,**{key:value.get() for key,value in values.items()},
                                             'stream':'stream1' if stream.get().startswith('High') else 'stream2'})
            except (ValueError,OSError) as problem:
                error.set(str(problem) if isinstance(problem,ValueError) else 'Could not save. Check folder permissions.')
                return
            self.camera_status.set('Camera settings saved. Start camera to connect.')
            dialog.destroy()
        ttk.Button(content,text='Save camera settings',command=save).pack(fill='x',pady=6)
        dialog.grab_set()

    def start_camera(self, offer_setup=True):
        if self.monitor or self.job:
            return
        try:
            settings = load_settings(ROOT/'camera.local.json')
            gallery = read_gallery()
            preview = self.preview.get()
            if not preview and not gallery:
                self.camera_status.set('Save a person first, or select Preview only to check the camera.')
                return
            watch = load_watch_names() & set(gallery)
            telegram = load_alert_settings() if self.notify.get() and not preview else None
            if self.notify.get() and not preview and not (telegram and watch):
                messagebox.showinfo('Telegram not armed','Pair a private Telegram chat and mark at least one profile. Recognition will run locally.')
            self.profiles = read_profiles()
            self.monitor = Monitor(settings,gallery,watch,telegram,preview,self.mode.get())
            self.start_button.configure(state='disabled')
            self.stop_button.configure(state='normal')
        except (ValueError,OSError) as error:
            self.camera_status.set(str(error))
            if offer_setup and not (ROOT/'camera.local.json').exists():
                self.configure_camera()

    def stop_camera(self):
        if self.monitor:
            self.monitor.stop.set()
            self.stop_button.configure(state='disabled')
            self.camera_status.set('Stopping camera…')
            if self.phone_remote:
                self.phone_remote.publish(None,'Camera stopped','No current video',0)

    def start_phone_remote(self):
        if self.phone_remote:
            return
        try:
            try:
                camera_host = load_settings(ROOT/'camera.local.json')['host']
            except (OSError,ValueError):
                camera_host = None
            address = lan_address(camera_host)
            if not address:
                raise ValueError('Could not find a local network address. Connect this computer to the rover network and retry.')
            self.stop_rover()
            remote = PhoneRemote(host='0.0.0.0',port=8765)
            remote.state.attach_rover(self.rover)
            self.phone_remote = remote
            self.phone_info.set(f'Open on your phone:\nhttp://{address}:{remote.port}/\n\nPairing code: {remote.pin}\n\nOne paired phone. Pairing another stops and replaces the previous session.')
            for button in self.direction_buttons:
                button.configure(state='disabled')
        except (OSError,ValueError):
            self.phone_info.set('Could not start sharing. Check the laptop network, and close any other phone-remote instance using port 8765. Camera setup is not required for driving.')

    def stop_phone_remote(self):
        remote = self.phone_remote
        self.phone_remote = None
        if remote:
            remote.close()
        for button in self.direction_buttons:
            button.configure(state='normal')
        self.phone_info.set('Off. Phone control stopped and the pairing session was closed.')

    def connect_rover(self):
        self.stop_rover()
        if self.phone_remote:
            self.phone_remote.state.attach_rover(None)
        if self.rover:
            self.rover.close()
            self.rover = None
        try:
            self.rover = RoverControl(self.address.get())
            if self.phone_remote:
                self.phone_remote.state.attach_rover(self.rover)
        except ValueError:
            self.rover_status.set('Enter the ESP32’s local IPv4 address.')

    def press(self, widget, direction):
        if self.phone_remote:
            return
        if self.rover and self.rover.hold(direction):
            self.held = widget,direction

    def stop_rover(self):
        self.held = None
        if getattr(self,'phone_remote',None):
            self.phone_remote.state.stop()
        if self.rover:
            self.rover.stop()

    def disconnect_rover(self):
        self.stop_rover()
        if getattr(self,'phone_remote',None):
            self.phone_remote.state.attach_rover(None)
        if self.rover:
            self.rover.close()
            self.rover = None
        self.rover_status.set('Disconnected')

    def tick(self):
        if self.held and self.rover:
            widget,direction = self.held
            released = sys.platform == 'win32' and not (ctypes.windll.user32.GetAsyncKeyState(1) & 0x8000)
            if released or self.root.winfo_containing(*self.root.winfo_pointerxy()) != widget or not self.rover.hold(direction):
                self.stop_rover()
        if self.rover:
            self.rover_status.set(self.rover.status)
        if self.job and self.job.done():
            future, done = self.job, self.job_done
            self.job = self.job_done = None
            try:
                done(future.result())
            except Exception as error:
                self.form.set(str(error))
        if self.monitor:
            with self.monitor.lock:
                frame,status,names,retrieved = self.monitor.latest
            if self.monitor.stop.is_set():
                frame,names,status = None,(),'Camera stopped'
            elif frame is not None and time.perf_counter() - retrieved > 2:
                frame,names,status = None,(),'Waiting for fresh video…'
            if not self.monitor.thread.is_alive():
                frame,names = None,()
                self.monitor = None
                self.start_button.configure(state='normal')
                self.stop_button.configure(state='disabled')
            self.camera_status.set(status)
            labels = [name + (f" ({self.profiles[name]['role']})" if self.profiles.get(name,{}).get('role') else '') for name in names]
            self.matches.set('Recognized: ' + ', '.join(labels) if labels else 'No live matches')
            if self.phone_remote:
                self.phone_remote.publish(frame,status,self.matches.get(),retrieved)
            if frame is not self.last_frame:
                self.last_frame = frame
                if frame is None:
                    self.video.configure(image='',text='No current video')
                    self.picture = None
                else:
                    image = Image.fromarray(frame)
                    image.thumbnail((max(320,self.video.winfo_width()),max(240,self.video.winfo_height())))
                    self.picture = ImageTk.PhotoImage(image)
                    self.video.configure(image=self.picture,text='')
        if self.phone_remote and not self.monitor:
            self.phone_remote.publish(None,self.camera_status.get(),'No current video',0)
        self.root.after(75,self.tick)

    def close(self):
        self.stop_rover()
        self.stop_phone_remote()
        if self.rover:
            self.rover.close()
        if self.monitor:
            self.monitor.stop.set()
            self.monitor.thread.join(timeout=3)
        self.pool.shutdown(wait=False,cancel_futures=True)
        self.root.destroy()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check',action='store_true')
    parser.add_argument('--preview',action='store_true')
    parser.add_argument('--start-camera',action='store_true')
    parser.add_argument('--phone',action='store_true',help='Start the paired phone remote on the local network')
    args = parser.parse_args()
    root = tk.Tk()
    if args.check:
        root.withdraw()
    app = App(root,args.preview)
    if args.check:
        FaceEngine()
        root.update_idletasks()
        app.close()
        print('Dashboard and face models initialized. No devices or alerts contacted.')
    else:
        if args.phone:
            if not app.names:
                app.preview.set(True)
            root.after(0,app.start_phone_remote)
        if args.preview or args.start_camera or args.phone:
            root.after(0,lambda:app.start_camera(offer_setup=not args.phone))
        root.mainloop()


if __name__ == '__main__':
    main()
