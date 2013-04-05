import z3
import simsym
import symtypes
import errno
import model

class SFn(simsym.SExpr, simsym.SymbolicConst):
    __z3_sort__ = z3.DeclareSort('Fn')

class SInum(simsym.SExpr, simsym.SymbolicConst):
    __z3_sort__ = z3.DeclareSort('Inum')

class SDataByte(simsym.SExpr, simsym.SymbolicConst):
    __z3_sort__ = z3.DeclareSort('DataByte')

SPid = simsym.SBool
SData = symtypes.tlist(SDataByte)
SFd = simsym.tstruct(inum = SInum, off = simsym.SInt)
SFdMap = symtypes.tdict(simsym.SInt, SFd)
SProc = symtypes.tstruct(fd_map = SFdMap)
SDirMap = symtypes.tdict(SFn, SInum)
SInode = simsym.tstruct(data = SData,
                        nlink = simsym.SInt,
                        atime = simsym.SInt,
                        mtime = simsym.SInt,
                        ctime = simsym.SInt,
                        ## XXX Directories impl:
                        # isdir = simsym.SBool,
                        # dirmap = SDirMap,
                       )
SIMap = symtypes.tmap(SInum, SInode)
## XXX Directories impl:
# SPathname = simsym.tstruct(last = SFn)
## XXX Non-directories impl:
SPathname = SFn

## Although some things are integers, we treat them as uninterpreted
## sorts in IsomorphicMatch, by checking what decl the integer is
## being assigned to.  The first part of the tuple is the decl, and
## the second is the fake uninterpreted sort name that these values
## will be treated as.  The sort name only matters for matching up
## with other sort names in this same list.  This results in an
## approximation; see also the comment about else clause handling
## in IsomorphicMatch.

pseudo_sort_decls = [
    (SInode.__z3_sort__.nlink, 'file-nlink'),
    (SData.__z3_sort__._len, 'file-length'),
]

## Ignore some pseudo sort names altogether when enumerating models.

pseudo_sort_ignore = {
    'file-nlink': True,     ## unused for test generation
    'file-length': True,    ## too many cases in link*link
    'fd-num': False,
}

def add_pseudo_sort_decl(decl, name):
    for d, _ in pseudo_sort_decls:
        if d.eq(decl): return
    pseudo_sort_decls.append((decl, name))

class Fs(model.Struct):
    __slots__ = ['i_map',
                 'proc0',
                 'proc1',

                 ## XXX Non-directories impl:
                 'root_dir',
                ]
    root_inum = SInum.any('Inum.root')

    def __init__(self):
        self.i_map = SIMap.any('Fs.imap')
        self.proc0 = SProc.any('Fs.proc0')
        self.proc1 = SProc.any('Fs.proc1')

        ## XXX Non-directories impl:
        self.root_dir = SDirMap.any('Fs.rootdir')

    def getproc(self, pid):
        if pid == False:
            return self.proc0
        return self.proc1

    def iused(self, inum):
        dir = SInum.any('dir')
        fn = SFn.any('fn')
        fd = simsym.SInt.any('fd')
        pid = SPid.any('pid')

        # If we try to simply index into dirmap, its __getitem__
        # won't have access to the supposition that it contains the right
        # key, and throw an exception.  Thus, we use _map directly.
        return simsym.symor([
            ## XXX Directories impl:
            # simsym.exists(dir,
            #     simsym.symand([
            #         self.i_map[dir].isdir,
            #         simsym.exists(fn,
            #             simsym.symand([self.i_map[dir].dirmap.contains(fn),
            #                            self.i_map[dir].dirmap._map[fn] == inum]))])),

            ## XXX Non-directories impl:
            simsym.exists(fn,
                simsym.symand([self.root_dir.contains(fn),
                               self.root_dir._map[fn] == inum])),

            simsym.exists(fd,
                simsym.symand([self.proc0.fd_map.contains(fd),
                               self.proc0.fd_map._map[fd].inum == inum])),

            simsym.exists(fd,
                simsym.symand([self.proc1.fd_map.contains(fd),
                               self.proc1.fd_map._map[fd].inum == inum])),
            ])

    def add_selfpid(self, pid):
        pass

    def add_fdvar(self, fdvar):
        add_pseudo_sort_decl(simsym.unwrap(fdvar).decl(), 'fd-num')

    def add_offvar(self, offvar):
        add_pseudo_sort_decl(simsym.unwrap(offvar).decl(), 'file-length')

    def nameiparent(self, pn):
        ## XXX Non-directories impl:
        return 0, self.root_dir, pn

        ## XXX Directories impl:
        # simsym.assume(self.i_map[self.root_inum].isdir)
        # return self.root_inum, self.i_map[self.root_inum].dirmap, pn.last

    @model.methodwrap(pn=SPathname,
                      creat=simsym.SBool,
                      excl=simsym.SBool,
                      trunc=simsym.SBool,
                      anyfd=simsym.SBool,
                      pid=SPid,
                      internal_alloc_inum=SInum,
                      internal_ret_fd=simsym.SInt,
                      internal_time=simsym.SInt,
                     )
    def open(self, pn, creat, excl, trunc, anyfd, pid,
             internal_alloc_inum, internal_ret_fd, internal_time):
        self.add_selfpid(pid)
        created = False
        anyfd = False
        _, pndirmap, pnlast = self.nameiparent(pn)
        if creat:
            if not pndirmap.contains(pnlast):
                simsym.assume(simsym.symnot(self.iused(internal_alloc_inum)))

                data_empty = SData.any('Data.empty')
                simsym.assume(data_empty._len == 0)
                idata = SInode.any()
                idata.data = data_empty
                idata.nlink = 1
                self.i_map[internal_alloc_inum] = idata
                pndirmap[pnlast] = internal_alloc_inum

                simsym.assume(internal_time > self.i_map[internal_alloc_inum].atime)
                simsym.assume(internal_time > self.i_map[internal_alloc_inum].mtime)
                simsym.assume(internal_time > self.i_map[internal_alloc_inum].ctime)
                self.i_map[internal_alloc_inum].atime = internal_time
                self.i_map[internal_alloc_inum].mtime = internal_time
                self.i_map[internal_alloc_inum].ctime = internal_time
                created = True
            else:
                if excl: return ('err', errno.EEXIST)
        if not pndirmap.contains(pnlast):
            return ('err', errno.ENOENT)

        inum = pndirmap[pnlast]
        if trunc:
            if not created:
                simsym.assume(internal_time > self.i_map[inum].mtime)
                simsym.assume(internal_time > self.i_map[inum].ctime)
                self.i_map[inum].mtime = internal_time
                self.i_map[inum].ctime = internal_time
            data_empty = SData.any('Data.empty')
            simsym.assume(data_empty._len == 0)
            self.i_map[inum].data = data_empty

        self.add_fdvar(internal_ret_fd)
        simsym.assume(internal_ret_fd >= 0)
        simsym.assume(simsym.symnot(self.getproc(pid).fd_map.contains(internal_ret_fd)))

        ## Lowest FD
        otherfd = simsym.SInt.any('fd')
        simsym.assume(simsym.symor([anyfd,
            simsym.symnot(simsym.exists(otherfd,
                simsym.symand([otherfd >= 0,
                               otherfd < internal_ret_fd,
                               self.getproc(pid).fd_map.contains(otherfd)])))]))

        fd_data = SFd.any()
        fd_data.inum = inum
        fd_data.off = 0
        self.getproc(pid).fd_map[internal_ret_fd] = fd_data

        return ('ok', internal_ret_fd)

    @model.methodwrap(src=SPathname, dst=SPathname,
                      internal_time=simsym.SInt)
    def rename(self, src, dst, internal_time):
        srcdiri, srcdirmap, srclast = self.nameiparent(src)
        dstdiri, dstdirmap, dstlast = self.nameiparent(dst)
        if not srcdirmap.contains(srclast):
            return ('err', errno.ENOENT)
        if srcdiri == dstdiri and srclast == dstlast:
            return ('ok',)
        if dstdirmap.contains(dstlast):
            dstinum = dstdirmap[dstlast]
        else:
            dstinum = None
        dstdirmap[dstlast] = srcdirmap[srclast]
        del srcdirmap[srclast]
        if dstinum is not None:
            self.i_map[dstinum].nlink = self.i_map[dstinum].nlink - 1
            simsym.assume(internal_time > self.i_map[dstinum].ctime)
            self.i_map[dstinum].ctime = internal_time
        return ('ok',)

    @model.methodwrap(pn=SPathname, internal_time=simsym.SInt)
    def unlink(self, pn, internal_time):
        _, dirmap, pnlast = self.nameiparent(pn)
        if not dirmap.contains(pnlast):
            return ('err', errno.ENOENT)
        inum = dirmap[pnlast]
        del dirmap[pnlast]
        self.i_map[inum].nlink = self.i_map[inum].nlink - 1
        simsym.assume(internal_time > self.i_map[inum].ctime)
        self.i_map[inum].ctime = internal_time
        return ('ok',)

    @model.methodwrap(oldpn=SPathname, newpn=SPathname, internal_time=simsym.SInt)
    def link(self, oldpn, newpn, internal_time):
        olddiri, olddirmap, oldlast = self.nameiparent(oldpn)
        newdiri, newdirmap, newlast = self.nameiparent(newpn)
        if not olddirmap.contains(oldlast):
            return ('err', errno.ENOENT)
        if newdirmap.contains(newlast):
            return ('err', errno.EEXIST)
        inum = olddirmap[oldlast]
        newdirmap[newlast] = inum
        self.i_map[inum].nlink = self.i_map[inum].nlink + 1
        simsym.assume(internal_time > self.i_map[inum].ctime)
        self.i_map[inum].ctime = internal_time
        return ('ok',)

    def iread(self, inum, off, time):
        simsym.assume(off >= 0)
        if off >= self.i_map[inum].data._len:
            return ('eof',)
        simsym.assume(time > self.i_map[inum].atime)
        self.i_map[inum].atime = time
        return ('data', self.i_map[inum].data[off])

    @model.methodwrap(fd=simsym.SInt, pid=SPid, internal_time=simsym.SInt)
    def read(self, fd, pid, internal_time):
        self.add_selfpid(pid)
        self.add_fdvar(fd)
        if not self.getproc(pid).fd_map.contains(fd):
            return ('err', errno.EBADF)
        off = self.getproc(pid).fd_map[fd].off
        r = self.iread(self.getproc(pid).fd_map[fd].inum, off, internal_time)
        if r[0] == 'data':
            self.getproc(pid).fd_map[fd].off = off + 1
        return r

    @model.methodwrap(fd=simsym.SInt, off=simsym.SInt, pid=SPid, internal_time=simsym.SInt)
    def pread(self, fd, off, pid, internal_time):
        self.add_selfpid(pid)
        self.add_fdvar(fd)
        self.add_offvar(off)
        if not self.getproc(pid).fd_map.contains(fd):
            return ('err', errno.EBADF)
        return self.iread(self.getproc(pid).fd_map[fd].inum, off, internal_time)

    def iwrite(self, inum, off, databyte, time):
        simsym.assume(off >= 0)
        ## Avoid overly-long files.  fs-test.py caps file size at 16 units.
        simsym.assume(off < 10)
        ## XXX Handle sparse files?
        simsym.assume(off <= self.i_map[inum].data._len)

        if off == self.i_map[inum].data._len:
            self.i_map[inum].data.append(databyte)
        else:
            self.i_map[inum].data[off] = databyte
        simsym.assume(time > self.i_map[inum].mtime)
        simsym.assume(time > self.i_map[inum].ctime)
        self.i_map[inum].mtime = time
        self.i_map[inum].ctime = time
        return ('ok',)

    @model.methodwrap(fd=simsym.SInt, databyte=SDataByte, pid=SPid, internal_time=simsym.SInt)
    def write(self, fd, databyte, pid, internal_time):
        self.add_selfpid(pid)
        self.add_fdvar(fd)
        if not self.getproc(pid).fd_map.contains(fd):
            return ('err', errno.EBADF)
        off = self.getproc(pid).fd_map[fd].off
        self.getproc(pid).fd_map[fd].off = off + 1
        return self.iwrite(self.getproc(pid).fd_map[fd].inum, off, databyte, internal_time)

    @model.methodwrap(fd=simsym.SInt, off=simsym.SInt, databyte=SDataByte, pid=SPid, internal_time=simsym.SInt)
    def pwrite(self, fd, off, databyte, pid, internal_time):
        self.add_selfpid(pid)
        self.add_fdvar(fd)
        self.add_offvar(off)
        if not self.getproc(pid).fd_map.contains(fd):
            return ('err', errno.EBADF)
        return self.iwrite(self.getproc(pid).fd_map[fd].inum, off, databyte, internal_time)

    def istat(self, inum):
        len = self.i_map[inum].data._len
        nlink = self.i_map[inum].nlink
        atime = self.i_map[inum].atime
        mtime = self.i_map[inum].mtime
        ctime = self.i_map[inum].ctime
        return ('ok', inum, len, nlink, atime, mtime, ctime)

    @model.methodwrap(pn=SPathname)
    def stat(self, pn):
        _, dirmap, pnlast = self.nameiparent(pn)
        if not dirmap.contains(pnlast):
            return ('err', errno.ENOENT)
        return self.istat(dirmap[pnlast])

    @model.methodwrap(fd=simsym.SInt, pid=SPid)
    def fstat(self, fd, pid):
        self.add_selfpid(pid)
        self.add_fdvar(fd)
        if not self.getproc(pid).fd_map.contains(fd):
            return ('err', errno.EBADF)
        return self.istat(self.getproc(pid).fd_map[fd].inum)

    @model.methodwrap(fd=simsym.SInt, pid=SPid)
    def close(self, fd, pid):
        self.add_selfpid(pid)
        self.add_fdvar(fd)
        if not self.getproc(pid).fd_map.contains(fd):
            return ('err', errno.EBADF)
        del self.getproc(pid).fd_map[fd]
        return ('ok',)

model_class = Fs
model_functions = [
    Fs.open,
    Fs.pread,
    Fs.pwrite,
    Fs.read,
    Fs.write,
    Fs.unlink,
    Fs.link,
    Fs.rename,
    Fs.stat,
    Fs.fstat,
    Fs.close,
]