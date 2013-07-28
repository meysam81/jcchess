#
#   usi.py
#
#   This file is part of gshogi   
#
#   gshogi is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   gshogi is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU General Public License for more details.
#
#   You should have received a copy of the GNU General Public License
#   along with gshogi.  If not, see <http://www.gnu.org/licenses/>.
#   

import gtk
import os, subprocess, thread
import time
import engine_debug, engine_output, gobject

class Usi:

    
    def __init__(self, verbose, verbose_usi, side):
    
        self.engine = 'gshogi'
        self.path = ''        
        self.engine_running = False
        self.newgame = False
        self.running_engine = ''         
        self.stop_pending = False
        self.ponder_move = None
        self.verbose = verbose 
        self.verbose_usi = verbose_usi
        self.side = side        
        self.engine_debug = engine_debug.get_ref()
        self.engine_output = engine_output.get_ref()        


    def start_engine(self, path):
        
        if path is None:
            path = self.path
            # if using builtin engine return (not USI)        
            if self.engine == 'gshogi':
                return       
 
        # path is the path to the USI engine executable
        if not os.path.isfile(path):
            print "invalid usipath:", path
            return False
 
        #
        # change the working directory to that of the engine before starting it
        #
        orig_cwd = os.getcwd()
        if self.verbose: print "current working directory is", orig_cwd        
        engine_wdir = os.path.dirname(path)
        os.chdir(engine_wdir)
        if self.verbose: print "working directory changed to" ,os.getcwd()

        # Attempt to start the engine as a subprocess
        if self.verbose: print "starting engine with path:",path
        p = subprocess.Popen(path, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE) 
        self.p = p    
        
        os.chdir(orig_cwd)
        if self.verbose: print "current working directory restored back to", os.getcwd()
        
        # check process is running
        i = 0
        while (p.poll() is not None):            
            i += 1
            if i > 40:        
                print "unable to start engine process"
                return False
            time.sleep(0.25)        

        if self.verbose: print "pid=",p.pid
        # start thread to read stdout
        self.op = []       
        self.soutt = thread.start_new_thread( self.read_stdout, () )
        
        # Tell engine to use the USI (universal shogi interface).        
        self.command('usi\n')       

        # wait for reply
        self.usi_option = []
        usi_ok = False
        i = 0
        while True:            
            for l in self.op:
                l = l.strip()
                #print l
                if l.startswith('option'):
                    self.usi_option.append(l)
                if l == 'usiok':
                    usi_ok = True
            self.op = []
            if usi_ok:
                break            
            i += 1
            if i > 40:                
                print "error - usiok not returned from engine"
                return False        
            time.sleep(0.25)

        # set pondering
        #self.command('setoption name USI_Ponder value false\n')
        if self.engine_manager.get_ponder():
            ponder_str = 'true'
        else:
            ponder_str = 'false' 
        self.command('setoption name USI_Ponder value ' + ponder_str + '\n')

        # set hash value 
        #self.command('setoption name USI_Hash value 256\n')
        self.command('setoption name USI_Hash value ' + str(self.engine_manager.get_hash_value()) + '\n')

        # Ask if ready
        self.command('isready\n')
        
        # wait for reply
        ready_ok = False
        i = 0
        while True:            
            for l in self.op:
                l = l.strip()
                #print l
                if l == 'readyok':
                    ready_ok = True
            self.op = []
            if ready_ok:
                break
            i += 1
            if i > 40:         
                print "error - readyok not returned from engine"
                return False        
            time.sleep(0.25)

        # Tell engine we are starting new game
        self.command('usinewgame\n')
        self.engine_running = True
        self.running_engine = self.engine

        return True

        
    def command(self, cmd):        
        e = self.side + '(' + self.get_running_engine().strip() + '):'
        if self.verbose or self.verbose_usi: print "->" + e + cmd.strip()
        gobject.idle_add(self.engine_debug.add_to_log, "->" + e + cmd.strip())        
        try:
            self.p.stdin.write(cmd)
        except AttributeError:           
            gobject.idle_add(self.engine_debug.add_to_log, "# engine process is not running")
        except IOError:            
            gobject.idle_add(self.engine_debug.add_to_log, "# engine process is not running")


    def stop_engine(self):        
        if not self.engine_running:
            return
 
        self.stop_pending = True
        engine_stopped = False

        try:
            if self.verbose: print "stopping engine" 
                     
            self.command('quit\n')

            # allow 2 seconds for engine process to end            
            i = 0
            while True:
                if self.p.poll() is not None:
                    engine_stopped = True
                    break                
                i += 1
                if i > 8:         
                    if self.verbose: print "engine has not terminated after quit command"
                    break        
                time.sleep(0.25)

            if not engine_stopped:
                if self.verbose: print "terminating engine subprocess pid ",self.p.pid
                # SIGTERM
                self.p.terminate()
                i = 0
                while True:
                    if self.p.poll() is not None:
                        engine_stopped = True
                        break                
                    i += 1
                    if i > 8:         
                        if self.verbose: print "engine has not responded to terminate command"
                        break        
                    time.sleep(0.25)

            if not engine_stopped:
                if self.verbose: print "killing engine subprocess pid ",self.p.pid
                # SIGKILL
                self.p.kill()
                i = 0
                while True:
                    if self.p.poll() is not None:
                        engine_stopped = True
                        break                
                    i += 1
                    if i > 16:         
                        if self.verbose: print "engine has not responded to kill command"
                        print "unable to stop engine pid",self.p.pid
                        break        
                    time.sleep(0.25)            
        except:                
            pass

        if self.verbose: print
        if engine_stopped: 
            if self.verbose: print "engine stopped ok"
        self.engine_running = False
        self.stop_pending = False
        self.running_engine = ''      


    def read_stdout(self):                
        while True:                  
            try:                
                self.p.stdout.flush()
                line = self.p.stdout.readline()
                line = line.strip()
                e = '<-' + self.side + '(' + self.get_running_engine().strip() + '):'
                if self.verbose or self.verbose_usi: print e + line
                gobject.idle_add(self.engine_debug.add_to_log, e+line)
                if line.startswith('info'):
                    gobject.idle_add(self.engine_output.add_to_log, self.side, self.get_running_engine().strip(), line)
                if line == '':
                    if self.verbose: print e + 'eof reached'
                    if self.verbose: print e + "stderr:",self.p.stderr.read()
                    break                
                self.op.append(line)
            except Exception, e:
                #line = e + 'error'
                print "subprocess error in usi.py read_stdout:",e                


    def check_running(self):
        # check if engine has changed since last use
        if self.engine != self.running_engine:
            if self.engine_running:
                self.stop_engine()
                self.start_engine(None)
                return

        if not self.engine_running:
            self.start_engine(None)
        else:
            if self.p.poll() is not None:
                print "warning engine has stopped running - attempting to restart"
                self.start_engine(None)


    def set_newgame(self):
        self.newgame = True


    # Ask engine to make move
    def cmove(self, movelist, side_to_move):
        self.check_running() 

        if self.newgame:      
            self.command('usinewgame\n')
            self.newgame = False
        
        startpos = self.game.get_startpos()

        # if not startpos must be sfen
        if startpos != 'startpos':
            startpos = 'sfen ' + startpos

        ml = ''
        for move in movelist:
            ml = ml + move + ' '        
        if ml == '':           
            b = 'position ' + startpos + '\n'           
        else:             
            b = 'position ' + startpos + ' moves ' + ml.strip() + '\n'           

        #b = 'position sfen lnsgkgsnl/1r5b1/ppppppppp/9/9/9/PPPPPPPPP/1B5R1/LNSGKGSNL b - 1 moves ' + ml.strip() +  '\n' 
        #b = 'position sfen 8l/1l+R2P3/p2pBG1pp/kps1p4/Nn1P2G2/P1P1P2PP/1PS6/1KSG3+r1/LN2+p3L w Sbgn3p 124 moves ' + ml.strip() +  '\n'        

        # Send the board position to the engine
        self.command(b)               

        # times in milliseconds
        #btime = time_left[0]
        #wtime = time_left[1]
        #byoyomi = time_left[2]     
    
        # clear the engine output window ready for next move
        gobject.idle_add(self.engine_output.clear, self.side, self.get_running_engine().strip())

        #print "calling time control module from usi module to get go command"
        gocmnd = self.tc.get_go_command(side_to_move)
        self.gocmnd = gocmnd        # save for possible ponder                  
        #print "go command:", gocmnd


        # start the clock
        #print "starting clock from usi.py"                
        self.tc.start_clock(side_to_move)
        
        # send the engine the command to do the move
        self.command(gocmnd + '\n')   
        

        #self.command('go btime ' + str(btime) +' wtime ' + str(wtime) + ' byoyomi ' + str(byoyomi) + '\n')        

        # Wait for move from engine
        i = 0
        bestmove = False                
        while True:            

            time.sleep(0.5)

            #i += 1
            #print "in cmove i=",i

            # if stop command sent while engine was thinking then return
            if not self.engine_running or self.stop_pending:
                return None, None            

            for l in self.op:
                l = l.strip()                    
                if l.startswith('bestmove'):
                    bestmove = l[9:].strip()
                    if self.verbose: print "bestmove is ",bestmove

                    # get ponder move if present
                    self.ponder_move = None
                    s = bestmove.find('ponder')
                    if s != -1:
                        self.ponder_move = bestmove[s + 7:].strip()
                        gobject.idle_add(self.engine_output.set_ponder_move, self.ponder_move, self.side)  # set ponder move in engine output window

                    # get bestmove
                    s = bestmove.find(' ')
                    if s != -1:        
                        bestmove = bestmove[:s]
                    self.op = []
        
                    # update time for last move
                    gtk.gdk.threads_enter()
                    #print "updating clock from usi.py"                    
                    self.tc.update_clock()                
                    self.gui.set_side_to_move(side_to_move)        
                    gtk.gdk.threads_leave()      

                    return bestmove, self.ponder_move            
            self.op = []


    def stop_ponder(self):
        # return if not pondering
        #if self.ponder_move is None:
        #    return 
        # stop pondering
        self.command('stop\n')
        # Wait for move from engine
        i = 0
        bestmove = False                
        while True:            

            time.sleep(0.5)

            #i += 1
            #print "in stop ponder i=",i

            # if stop command sent while engine was thinking then return
            if not self.engine_running or self.stop_pending:
                return None, None            

            for l in self.op:
                l = l.strip()                    
                if l.startswith('bestmove'):
                    bestmove = l[9:].strip()
                    if self.verbose: print "ponder bestmove is ",bestmove

                    # get ponder move if present
                    ponder_move = None
                    s = bestmove.find('ponder')
                    if s != -1:
                        ponder_move = bestmove[s + 7:].strip()                     

                    # get bestmove
                    s = bestmove.find(' ')
                    if s != -1:        
                        bestmove = bestmove[:s]
                    self.op = []                  

                    return bestmove, ponder_move            
            self.op = []            


    def send_ponderhit(self, side_to_move):

        # start the clock                       
        self.tc.start_clock(side_to_move)

        self.command('ponderhit\n')
        # Wait for move from engine
        i = 0
        bestmove = False                
        while True:            

            time.sleep(0.5)

            #i += 1
            #print "in send ponder i,side=",i,self.side

            # if stop command sent while engine was thinking then return
            if not self.engine_running or self.stop_pending:
                return None, None            

            for l in self.op:
                l = l.strip()                    
                if l.startswith('bestmove'):
                    bestmove = l[9:].strip()
                    if self.verbose: print "bestmove is ",bestmove

                    # get ponder move if present
                    self.ponder_move = None
                    s = bestmove.find('ponder')
                    if s != -1:
                        self.ponder_move = bestmove[s + 7:].strip()                     
                        gobject.idle_add(self.engine_output.set_ponder_move, self.ponder_move, self.side)  # set ponder move in engine output window

                    # get bestmove
                    s = bestmove.find(' ')
                    if s != -1:        
                        bestmove = bestmove[:s]
                    self.op = []
        
                    # update time for last move
                    gtk.gdk.threads_enter()
                    #print "updating clock from usi.py"                    
                    self.tc.update_clock()                
                    self.gui.set_side_to_move(side_to_move)        
                    gtk.gdk.threads_leave()      

                    return bestmove, self.ponder_move            
            self.op = []            


    def start_ponder(self, pondermove, movelist, cmove):       

        startpos = self.game.get_startpos()

        # if not startpos must be sfen
        if startpos != 'startpos':
            startpos = 'sfen ' + startpos

        ml = ''
        for move in movelist:
            ml = ml + move + ' '        
        #if ml == '':
        #    print "error empty movelist in ponder in usi.py"
        #    return
                 
        ml = ml.strip()
        ml = ml + ' ' + cmove + ' ' + pondermove
        ml = ml.strip()
 
        # create the position string with the ponder move added
        b = 'position ' + startpos + ' moves ' + ml + '\n'       

        # Send the board position to the engine
        self.command(b)
        
        pondercmd = 'go ponder' + self.gocmnd[2:]                 
        self.command(pondercmd + '\n')

        # clear the engine output window ready for next move
        gobject.idle_add(self.engine_output.clear, self.side, self.get_running_engine().strip())

        return


    def get_options(self):
        return self.usi_option


    def set_options(self, options):
        self.usi_option = options       


    def set_option(self, option):
        option = option + '\n'        
        self.command(option)


    # used when adding new engines in engine_manager
    def test_engine(self, path):
        msg = ''
        name = ''

        # path is the path to the USI engine executable
        if not os.path.isfile(path):
            msg = "invalid path " + path
            return msg, name

        running = self.engine_running
        if running:
            self.stop_engine()

        # Attempt to start the engine as a subprocess
        try:
            p = subprocess.Popen(path, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE) 
        except OSError, oe:            
            msg = "error starting engine: " + "OSError" + str(oe)
            return msg, name
        self.p = p        

        # check process is running
        i = 0
        while (p.poll() is not None):            
            i += 1
            if i > 40:        
                msg = "not a valid USI engine"
                return msg, name     
            time.sleep(0.25)   

        # start thread to read stdout
        self.op = []       
        self.soutt = thread.start_new_thread( self.read_stdout, () )
        
        # Tell engine to use the USI (universal shogi interface).
        self.command('usi\n')        

        # wait for reply
        self.usi_option = []
        usi_ok = False
        i = 0
        while True:            
            for l in self.op:
                l = l.strip()               
                if l.startswith('id '):                   
                    w = l.split()                   
                    if w[1] == 'name':
                        w.pop(0)
                        w.pop(0)
                        for j in w:
                            name = name + j + ' '
                        name.strip()                    
                    self.usi_option.append(l)
                if l == 'usiok':
                    usi_ok = True
            self.op = []
            if usi_ok:
                break            
            i += 1
            if i > 40:                
                msg = "not a valid USI engine"
                return msg, name       
            time.sleep(0.25)

        try:                    
            self.command('quit\n')            
            self.p.terminate()
        except:                
            pass

        return msg, name    


    def set_engine(self, ename, path):
        self.engine = ename
        if path == None:
            self.path = self.engine_manager.get_path(ename)
        else:    
            self.path = path        


    def set_path(self, epath):
        self.path = epath


    def get_engine(self):
        return self.engine    

   
    def get_running_engine(self):
        if self.running_engine == '':
            return self.engine
        else:    
            return self.running_engine    


    def USI_options(self, b):
        self.check_running() 
        options = self.get_options()        
       
        wdgts = []
        opt_i = -1
        for option in options:            
            opt_i += 1            
            name = ''
            otype = ''
            default = ''
            minimum = ''
            maximum = ''
            userval = ''
            try:
                words = option.split()
                w = words.pop(0)
                if w != 'option':
                    if self.verbose: print 'invalid option line ignored:',option
                    continue

                w = words.pop(0)
                if w != 'name':
                    if self.verbose: print 'invalid option line ignored:',option
                    continue

                name = words.pop(0)

                w = words.pop(0)
                if w != 'type':
                    if self.verbose: print 'invalid option line ignored:',option
                    continue

                otype = words.pop(0)               
                
                uvars = []
                while True:                
                    w = words.pop(0)
                    w2 = words.pop(0)                    
                    if w == 'default':
                        default = w2
                    elif w == 'min':
                        minimum = w2
                    elif w == 'max':
                        maximum = w2
                    elif w == 'var':
                        uvars.append(w2)
                    elif w == 'userval':
                        userval = w2                    
                    else:
                        if self.verbose: print 'error parsing option:', option

            except IndexError:                
                pass

            wdgts.append((opt_i, name, otype, default, minimum, maximum, uvars, userval))            
       

        diagtitle = self.get_engine()
        dialog = gtk.Dialog(diagtitle, None, 0, (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL, gtk.STOCK_OK, gtk.RESPONSE_OK))  
        wlist = []
        for w in wdgts:            
            opt_i, name, otype, default, minimum, maximum, uvars, userval = w
            if otype == 'spin':                 
                if minimum == '':
                    minimum = 0
                if maximum == '':
                    maximum = 10
                if default == '':
                    default = minimum
                if userval != '':
                    default = userval
                adj = gtk.Adjustment(float(default), float(minimum), float(maximum), 1, 5, 0)               
                spinner = gtk.SpinButton(adj, 1.0, 0)
                #spinner.set_width_chars(14)
                al = gtk.Alignment(xalign=1.0, yalign=0.0, xscale=0.0, yscale=0.0)
                al.add(spinner)                    
    
                lbl = gtk.Label(name + ':')

                hb = gtk.HBox(False, 0)
                hb.pack_start(lbl, False, False, 0)
                hb.pack_start(al, True, True, 10)

                dialog.vbox.pack_start(hb, False, True, 0)               
        
                v = (opt_i, adj, name, otype)
                wlist.append(v)

                lbl.show()
                spinner.show()
                al.show()
                hb.show()
            elif otype == 'string':               
                ent = gtk.Entry()
                if userval != '':
                    default = userval
                ent.set_text(default)

                al = gtk.Alignment(xalign=1.0, yalign=0.0, xscale=0.0, yscale=0.0)
                al.add(ent)

                lbl = gtk.Label(name + ':')

                hb = gtk.HBox(False, 0)
                hb.pack_start(lbl, False, False, 0)
                hb.pack_start(al, True, True, 10)

                dialog.vbox.pack_start(hb, False, True, 0) 

                v = (opt_i, ent, name, otype)
                wlist.append(v)

                lbl.show()
                ent.show()
                al.show()
                hb.show()
            elif otype == 'check':              
                cb = gtk.CheckButton(label=None, use_underline=True)
                if userval != '':
                    default = userval
                if default == 'true':                
                    cb.set_active(True)
                else:
                    cb.set_active(False)
                al = gtk.Alignment(xalign=1.0, yalign=0.0, xscale=0.0, yscale=0.0)
                al.add(cb)

                lbl = gtk.Label(name + ':')
                hb = gtk.HBox(False, 0)
                hb.pack_start(lbl, False, False, 0)
                hb.pack_start(al, True, True, 10)

                dialog.vbox.pack_start(hb, False, True, 0) 

                v = (opt_i, cb, name, otype)
                wlist.append(v)
                
                lbl.show()
                cb.show()
                al.show()
                hb.show()
            elif otype == 'combo':
                if userval != '':
                    default = userval                
                combobox = gtk.combo_box_new_text()
                i = 0
                for v in uvars: 
                    combobox.append_text(v)
                    if v == default:
                        combobox.set_active(i)
                    i += 1

                al = gtk.Alignment(xalign=1.0, yalign=0.0, xscale=0.0, yscale=0.0)
                al.add(combobox)
                al.show() 
                combobox.show()

                lbl = gtk.Label(name + ':')
                hb = gtk.HBox(False, 0)
                hb.pack_start(lbl, False, False, 0)
                hb.pack_start(al, True, True, 10)

                dialog.vbox.pack_start(hb, False, True, 0)

                v = (opt_i, combobox, name, otype)
                wlist.append(v)
 
                lbl.show()                                
                hb.show()
            else:
                if self.verbose: print "type ignored - ",otype 
        
        dialog.set_default_response(gtk.RESPONSE_OK)
        response = dialog.run()
        if response == gtk.RESPONSE_OK:
            for w in wlist:               
                opt_i, widge, name, otype = w                
                if otype == 'spin':    
                    av = int(widge.value)
                elif otype == 'string':
                    av = widge.get_text()
                elif otype == 'check':
                    if widge.get_active():
                        av = 'true'
                    else:
                        av = 'false'
                elif otype == 'combo': 
                    av = widge.get_active_text()                   
                else:
                    if self.verbose: print "unknown type", otype
                #setoption name <id> [value <x>]
                #usi.set_option('option name LimitDepth type spin default 10 min 4 max 10')    
                a = 'setoption name ' + name + ' value ' + str(av)
                #print "a=",a                
                self.set_option(a)
                u = options[opt_i].find('userval')
                if u == -1:
                    options[opt_i] = options[opt_i] +  ' userval ' + str(av)
                else:                   
                    options[opt_i] = options[opt_i][0:u] + 'userval ' + str(av)                                                
            self.set_options(options) 
        dialog.destroy()


    def set_refs(self, game, em, gui, tc):
        self.game = game 
        self.engine_manager = em
        self.gui = gui
        self.tc = tc                
        


