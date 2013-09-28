# -*- coding: utf-8 -*-
# Copyright (C) 2012, the IEP development team
#
# IEP is distributed under the terms of the (new) BSD License.
# The full license can be found in 'license.txt'.

""" 
Module to integrate GUI event loops in the IEP interpreter.

This specifies classes that all have the same interface. Each class
wraps one GUI toolkit.

Support for PyQt4, WxPython, FLTK, GTK, TK.

"""

import time

from iepkernel import printDirect



mainloopWarning = """
Note: not entering main loop. The GUI app is integrated with the IEP event
loop, which means that the function to enter the main loop does not block. 
If your app crashes, this might be because a GUI object goes out of scope 
and is prematurely cleaned up.
""".strip()


class App_base:
    """ Defines the interface. 
    """
    
    def process_events(self):
        pass
    
    def run(self, repl_callback, sleeptime=0.01):
        """ Very simple mainloop. Subclasses can overload this to use
        the native event loop. Attempt to process GUI events at least 
        every sleeptime seconds.
        """
        while True:
            time.sleep(sleeptime)
            repl_callback()
            self.process_events()
    
    def quit(self):
        raise SystemExit()



class App_tk(App_base):    
    """ Tries to import tkinter and returns a withdrawn tkinter root
    window.  If tkinter is already imported or not available, this
    returns None.  
    Modifies tkinter's mainloop with a dummy so when a module calls
    mainloop, it does not block.
    """    
    def __init__(self):
        
        # Try importing
        import sys
        if sys.version[0] == '3':
            import tkinter
        else:
            import Tkinter as tkinter
        
        # Replace mainloop. Note that a root object obtained with
        # tkinter.Tk() has a mainloop method, which will simply call
        # tkinter.mainloop().
        def dummy_mainloop(*args,**kwargs):
            printDirect(mainloopWarning)
        tkinter.Misc.mainloop = dummy_mainloop
        tkinter.mainloop = dummy_mainloop
                
        # Create tk "main window" that has a Tcl interpreter.
        # Withdraw so it's not shown. This object can be used to
        # process events for any other windows.
        r = tkinter.Tk()
        r.withdraw()
        
        # Store the app instance to process events
        self.app = r
        
        # Notify that we integrated the event loop
        self.app._in_event_loop = 'IEP'
        tkinter._in_event_loop = 'IEP'
    
    def process_events(self):
        self.app.update()



class App_fltk(App_base):
    """ Hijack fltk 1.
    This one is easy. Just call fl.wait(0.0) now and then.
    Note that both tk and fltk try to bind to PyOS_InputHook. Fltk
    will warn about not being able to and Tk does not, so we should
    just hijack (import) fltk first. The hook that they try to fetch
    is not required in IEP, because the IEP interpreter will keep
    all GUI backends updated when idle.
    """
    def __init__(self):
        # Try importing        
        import fltk as fl
        import types
        
        # Replace mainloop with a dummy
        def dummyrun(*args,**kwargs):
            printDirect(mainloopWarning)
        fl.Fl.run = types.MethodType(dummyrun, fl.Fl)
        
        # Store the app instance to process events
        self.app =  fl.Fl   
        
        # Notify that we integrated the event loop
        self.app._in_event_loop = 'IEP'
        fl._in_event_loop = 'IEP'
    
    def process_events(self):
        self.app.wait(0)



class App_fltk2(App_base):
    """ Hijack fltk 2.    
    """
    def __init__(self):
        # Try importing
        import fltk2 as fl        
        
        # Replace mainloop with a dummy
        def dummyrun(*args,**kwargs):
            printDirect(mainloopWarning)    
        fl.run = dummyrun    
        
        # Return the app instance to process events
        self.app = fl
        
        # Notify that we integrated the event loop
        self.app._in_event_loop = 'IEP'
    
    def process_events(self):
        # is this right?
        self.app.wait(0) 



class App_qt(App_base):
    """ Common functionality for pyqt and pyside
    """
    
    
    def __init__(self):
        import types
        
        # Try importing qt        
        QtGui, QtCore = self.importCoreAndGui()
        self._QtGui, self._QtCore = QtGui, QtCore
        
        # Store the real application class
        if not hasattr(QtGui, 'real_QApplication'):
            QtGui.real_QApplication = QtGui.QApplication
        
        
        class QApplication_hijacked(QtGui.QApplication):
            """ QApplication_hijacked(*args, **kwargs)
            
            Hijacked QApplication class. This class has a __new__() 
            method that always returns the global application 
            instance, i.e. QtGui.qApp.
            
            The QtGui.qApp instance is an instance of the original
            QtGui.QApplication, but with its __init__() and exec_() 
            methods replaced.
            
            You can subclass this class; the global application instance
            will be given the methods and attributes so it will behave 
            like the subclass.
            """
            def __new__(cls, *args, **kwargs):
                
                # Get the singleton application instance
                theApp = QApplication_hijacked.instance()
                
                # Instantiate an original QApplication instance if we need to
                if theApp is None:
                    theApp = QtGui.real_QApplication(*args, **kwargs)
                    QtGui.qApp = theApp
                
                # Add attributes of cls to the instance to make it
                # behave as if it were an instance of that class
                for key in dir(cls):
                    # Skip all magic methods except __init__
                    if key.startswith('__') and key != '__init__':
                        continue
                    # Skip attributes that we already have
                    val = getattr(cls, key)
                    if hasattr(theApp.__class__, key):
                        if hash(val) == hash(getattr(theApp.__class__, key)):
                            continue
                    # Make method?
                    if hasattr(val, '__call__'):
                        if hasattr(val, 'im_func'):
                            val = val.im_func # Python 2.x
                        val = types.MethodType(val, theApp.__class__)
                    # Set attribute on app instance (not the class!)
                    try:
                        setattr(theApp, key, val)
                    except Exception:
                        pass # tough luck
                
                # Call init function (in case the user overloaded it)
                theApp.__init__(*args, **kwargs)
                
                # Return global app object (modified to the users needs)
                return theApp
            
            def __init__(self, *args, **kwargs):
               pass
            
            def exec_(self, *args, **kwargs):
                """ This function does nothing, except printing a
                warning message. The point is that a Qt App can crash
                quite hard if an object goes out of scope, and the error
                is not obvious.
                """
                printDirect(mainloopWarning)
                # todo: is it really necessary to hide this? Can we not enter
                # the mainloop twice?
            
            def quit(self, *args, **kwargs):
                """ Do not quit. """
                pass
        
        
        # Instantiate application object 
        self.app = QApplication_hijacked([''])
        
        # Keep it alive even if all windows are closed
        self.app.setQuitOnLastWindowClosed(False)
        
        # Replace app class
        QtGui.QApplication = QApplication_hijacked
        
        # Notify that we integrated the event loop
        self.app._in_event_loop = 'IEP'
        QtGui._in_event_loop = 'IEP'
    
    
    def process_events(self):
        self.app.flush()
        self.app.processEvents()
    
    
    def run(self, repl_callback, sleeptime=None):
        # Create timer 
        timer = self._timer = self._QtCore.QTimer()
        timer.setSingleShot(False)
        timer.setInterval(0.05*1000)  # ms
        timer.timeout.connect(repl_callback)
        timer.start()
        
        # Enter Qt mainloop
        #self._QtGui.real_QApplication.exec_(self.app)
        self._QtGui.real_QApplication.exec_()
    
    
    def quit(self):
        self._QtGui.real_QApplication.quit()



class App_pyqt4(App_qt):
    """ Hijack the PyQt4 mainloop.
    """
    
    def importCoreAndGui(self):
        # Try importing qt        
        import PyQt4
        from PyQt4 import QtGui, QtCore
        return QtGui, QtCore
    
    
class App_pyside(App_qt):
    """ Hijack the PySide mainloop.
    """
    
    def importCoreAndGui(self):
        # Try importing qt        
        import PySide
        from PySide import QtGui, QtCore
        return QtGui, QtCore



class App_wx(App_base):
    """ Hijack the wxWidgets mainloop.    
    """ 
    
    def __init__(self):
        
        # Try importing
        try:
            import wx
        except ImportError:            
            # For very old versions of WX
            import wxPython as wx
        
        # Create dummy mainloop to replace original mainloop
        def dummy_mainloop(*args, **kw):
            printDirect(mainloopWarning)
        
        # Depending on version, replace mainloop
        ver = wx.__version__
        orig_mainloop = None
        if ver[:3] >= '2.5':
            if hasattr(wx, '_core_'): core = getattr(wx, '_core_')
            elif hasattr(wx, '_core'): core = getattr(wx, '_core')
            else: raise ImportError
            orig_mainloop = core.PyApp_MainLoop
            core.PyApp_MainLoop = dummy_mainloop
        elif ver[:3] == '2.4':
            orig_mainloop = wx.wxc.wxPyApp_MainLoop
            wx.wxc.wxPyApp_MainLoop = dummy_mainloop
        else:
            # Unable to find either wxPython version 2.4 or >= 2.5."
            raise ImportError
        
        # Store package wx
        self.wx = wx
        
        # Get and store the app instance to process events 
        app = wx.GetApp()
        if app is None:
            app = wx.App(False)
        self.app = app
        
        # Notify that we integrated the event loop
        self.app._in_event_loop = 'IEP'
        wx._in_event_loop = 'IEP'
    
    def process_events(self):
        wx = self.wx
        
        # This bit is really needed        
        old = wx.EventLoop.GetActive()                       
        eventLoop = wx.EventLoop()
        wx.EventLoop.SetActive(eventLoop)                        
        while eventLoop.Pending():
            eventLoop.Dispatch()
        
        # Process and reset
        self.app.ProcessIdle() # otherwise frames do not close
        wx.EventLoop.SetActive(old)   



class App_gtk(App_base):
    """ Modifies pyGTK's mainloop with a dummy so user code does not
    block IPython.  processing events is done using the module'
    main_iteration function.
    """
    def __init__(self):
        # Try importing gtk
        import gtk
        
        # Replace mainloop with a dummy
        def dummy_mainloop(*args, **kwargs):
            printDirect(mainloopWarning)        
        gtk.mainloop = dummy_mainloop
        gtk.main = dummy_mainloop
        
        # Replace main_quit with a dummy too
        def dummy_quit(*args, **kwargs):
            pass        
        gtk.main_quit = dummy_quit
        gtk.mainquit = dummy_quit
        
        # Make sure main_iteration exists even on older versions
        if not hasattr(gtk, 'main_iteration'):
            gtk.main_iteration = gtk.mainiteration
        
        # Store 'app object'
        self.app = gtk
        
        # Notify that we integrated the event loop
        self.app._in_event_loop = 'IEP'
    
    def process_events(self):
        gtk = self.app
        while gtk.events_pending():            
            gtk.main_iteration(False)
