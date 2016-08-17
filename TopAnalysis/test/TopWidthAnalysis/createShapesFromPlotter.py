import os
import sys
import optparse
import ROOT
import commands
import getpass
import pickle
import numpy


ROOT.gSystem.Load("libHiggsAnalysisCombinedLimit")
ROOT.gROOT.SetBatch()

def replaceBadCharacters(inputStr):
    newStr = inputStr
    for token in ['+','-','*',' ','#','{','(',')','}','@']:
        newStr=newStr.replace(token,'')
    return newStr

"""
test if variation is significant enough i.e. if sum_{bins} |var-nom| > tolerance
"""
def acceptVariationForDataCard(nomH,upH,downH,tol=1e-2):
    diffUp,diffDown=0,0
    for xbin in xrange(1,nomH.GetNbinsX()):
        val,valUp,valDown=nomH.GetBinContent(xbin),upH.GetBinContent(xbin),downH.GetBinContent(xbin)
        diffUp+=ROOT.TMath.Abs(valUp-val)
        diffDown+=ROOT.TMath.Abs(valDown-val)
    accept = True if (diffUp>tol or diffDown>tol) else False
    return accept

"""
in case of multiple signals, remove others
"""
def filterShapeList(exp,signalList,rawSignalList):
    newExp={}
    for key in exp:

        matchFound=False
        for rawKey in rawSignalList:
            if rawKey in key:
                matchFound=True
        if matchFound and not key in signalList : continue

        newExp[key]=exp[key]
    return newExp


"""
get distributions from file
"""
def getDistsFrom(directory,addList=None,addTitle='',keyFilter=''):
    obs=None
    exp={}
    dirName=directory.GetName()
    addedHistProduced=False
    for key in directory.GetListOfKeys():
        if len(keyFilter)>0 and key.GetName()!='%s_%s'%(dirName,keyFilter) : continue
        obj=directory.Get(key.GetName())
        if not obj.InheritsFrom('TH1') : continue
        inAddList = False;
        if obj.GetName()==dirName :
            obs=obj.Clone('data_obs')
            obs.SetDirectory(0)
        else :
            newName=obj.GetName().split(dirName+'_')[-1]
            for token in ['+','-','*',' ','#','{','(',')','}','@']:
                newName=newName.replace(token,'')
            if addList and newName in addList :
                newName='added' if addTitle == '' else addTitle
                if addedHistProduced :
                    exp[newName].Add(obj)
                    addedHistProduced = True;
                    inAddList=True
                else :
                    exp[newName] = obj.Clone(newName)
            else :
                exp[newName]=obj.Clone(newName)
                exp[newName].SetDirectory(0)

            #newName = ('added' if addTitle == '' else addTitle) if inAddList and addedHistProduced else newName
            if obj.InheritsFrom('TH2'):
                for xbin in xrange(1,exp[newName].GetNbinsX()+1):
                    for ybin in xrange(1,exp[newName].GetNbinsY()+1):
                        binContent=exp[newName].GetBinContent(xbin,ybin)
                        if binContent>0: continue
                        newBinContent=ROOT.TMath.Max(ROOT.TMath.Abs(binContent),1e-3)
                        exp[newName].SetBinContent(xbin,ybin,newBinContent)
                        exp[newName].SetBinError(xbin,ybin,newBinContent)
            else:
                for xbin in xrange(1,exp[newName].GetNbinsX()+1):
                    binContent=exp[newName].GetBinContent(xbin)
                    if binContent>0: continue
                    newBinContent=ROOT.TMath.Max(ROOT.TMath.Abs(binContent),1e-3)
                    exp[newName].SetBinContent(xbin,newBinContent)
                    exp[newName].SetBinError(xbin,newBinContent)
    return obs,exp

"""
merge many directories with the same directory base-name
  '.' --> 'p'
"""
def getMergedDists(fIn,basedir='',addList=None,addTitle='',
                   widList=None,nomWid='',sigList=None,keyFilter=''):
    obs=None
    exp={}
    for wid in widList :
        dirName='%s%s'%(basedir,wid)
        #print dirName
        directory = fIn.Get(dirName)
        if wid == nomWid :
            obs,mergeExp=getDistsFrom(directory=directory,addList=addList,addTitle=addTitle,keyFilter=keyFilter)
            for key in mergeExp :
                newName=key
                if key in sigList :
                    newName=('%s%s'%(key,wid.replace('.','p')))
                exp[newName]=mergeExp[key].Clone(newName)
        else :
            _,mergeExp=getDistsFrom(directory=directory,addList=addList,addTitle=addTitle,keyFilter=keyFilter)
            for key in mergeExp :
                if key in sigList :
                    newName=('%s%s'%(key,wid.replace('.','p')))
                    exp[newName]=mergeExp[key].Clone(newName)
                else : continue
    return obs,exp


"""
save distributions to file
"""
def saveToShapesFile(outFile,shapeColl,directory=''):
    fOut=ROOT.TFile.Open(outFile,'UPDATE')
    if len(directory)==0:
        fOut.cd()
    else:
        if not fOut.Get(directory):
            fOut.mkdir(directory)
        outDir=fOut.Get(directory)
        outDir.cd()
    for key in shapeColl:
        #remove bin labels
        shapeColl[key].GetXaxis().Clear()

        #convert to TH1D (projections are TH1D)
        if not shapeColl[key].InheritsFrom('TH1D') :
            h=ROOT.TH1D()
            shapeColl[key].Copy(h)
            shapeColl[key]=h

        shapeColl[key].Write(key,ROOT.TObject.kOverwrite)
    fOut.Close()

"""
make an MC truth dataset (sigs+bkgs)
"""
def makeMCTruthHist(hypothesis,sigList,dists):
    outputHist=None
    firstLoop=True
    print "Producing MC Truth data for hypothesis %s"%hypothesis

    for sig in sigList :
        sigHist=dists["%s%s"%(sig,hypothesis)].Clone()
        if firstLoop :
            outputHist=sigHist.Clone()
            firstLoop=False
        else :
            outputHist.Add(sigHist)
    for dist in dists :
        isSig=False
        for sig in sigList :
            if sig in dist : isSig=True
        if isSig : continue
        bkgHist=dists[dist].Clone()
        outputHist.Add(sigHist)
    return outputHist

"""
steer the script
"""
def main():

    #configuration
    usage = 'usage: %prog [options]'
    parser = optparse.OptionParser(usage)
    parser.add_option('-i', '--input',     dest='input',     help='input plotter',                            default=None,            type='string')
    parser.add_option(      '--systInput', dest='systInput', help='input plotter for systs from alt samples', default=None,            type='string')
    parser.add_option('-d', '--dists',     dest='distList',  help='distribution',        default='minmlb,mdrmlb,incmlb,sncmlb,mt2mlb', type='string')
    parser.add_option('-s', '--signal',    dest='signal',    help='signal (csv)',                             default='tbart,tW',      type='string')
    parser.add_option('-c', '--cat',       dest='cat',       help='categories (csv)',                         default='1b,2b',         type='string')
    parser.add_option('-o', '--output',    dest='output',    help='output directory',                         default='datacards',     type='string')
    parser.add_option(      '--addSigs',   dest='addSigs',   help='signal processes to add',                  default=False,     action='store_true')
    parser.add_option(      '--lfs',       dest='lfsInput',  help='lepton final states to consider',          default='EE,EM,MM',      type='string')
    parser.add_option(      '--lbCat',     dest='lbCat',     help='pt categories to consider',                default='highpt,lowpt',  type='string')
    parser.add_option(      '--truth', dest='truthDataset',  help='make data out of MC truth',                default='',              type='string')
    parser.add_option('-w', '--wids',  dest='widList',       help='signal widths',  default='0.5,1.0,1.5,2.0,2.5,3.0,3.5,4.0,4.5,5.0', type='string')
    parser.add_option('--noshapes', dest='skipMakingShapes', help='jump straight to morphing',                     default=False, action='store_true')
    parser.add_option('--nomorph',  dest='skipMorphing',     help='do not morph signal dists',                     default=False, action='store_true')
    parser.add_option('--allmorph', dest='allMorphs',        help='make morph validation plots for all cats',      default=False, action='store_true')
    parser.add_option('--makesens', dest='makeSens',         help='make local sensitivity validation (very slow)', default=False, action='store_true')
    parser.add_option('--novalidation', dest='noValidation', help='do not make any validation plots',              default=False, action='store_true')
    (opt, args) = parser.parse_args()

    # parse the dists to consider
    distList = opt.distList.split(',')

    # parse the channels, pt(l,b), b categories to consider
    lfsList=opt.lfsInput.split(',')
    lbCatList=opt.lbCat.split(',')
    catList=opt.cat.split(',')

    # what are our signal processes?
    rawSignalList=opt.signal.split(',')
    signalList = { 'top' } if opt.addSigs else rawSignalList[:]

    # what are our widths?
    rawWidList = opt.widList.split(',')
    widList = rawWidList[:]
    for i in xrange(0,len(rawWidList)) :
        widList[i] = ('%sw'%(rawWidList[i]))
    nomWid="1.0w"
    modNomWid="1p0w"

    modWidList=widList[:]
    for i in xrange(0,len(widList)) :
        modWidList[i]=widList[i].replace('.','p')

    # HARDCODE systematics
    tWRateSystList=['tW']
    ttRateSystList=['tbart']
    tWIsSig=('tW'    in rawSignalList)
    ttIsSig=('tbart' in rawSignalList)
    for wid in modWidList :
        if tWIsSig : tWRateSystList += ["tW%s"%wid]
        if ttIsSig : ttRateSystList += ["tbart%s"%wid]

    rateSysts=[
          ('lumi_13TeV',       1.062,    'lnN',    []                   ,['Multijetsdata']),
          ('DYnorm_th',        1.30,     'lnN',    ['DY']  ,[]),
          ('Wnorm_th',         1.30,     'lnN',    ['W']   ,[]),
          ('tWnorm_th',        1.054,    'lnN',    tWRateSystList,[]),
          ('tnorm_th',         1.044,    'lnN',    ['tch']              ,[]),
          ('VVnorm_th',        1.20,     'lnN',    ['Multiboson']       ,[]),
          ('tbartVnorm_th',    1.30,     'lnN',    ['tbartV']           ,[]),
    ]

    Mtop       =['tbartm=169.5','tbartm=175.5','tWm=169.5','tWm=175.5']
    ttParton_tt=['tbartscaledown','tbartscaleup']
    ttParton_tW=['tWscaledown','tWscaleup']
    ME={    "muF": ['%sgen%i'%(sig,ind) for sig in ['tbart','tW'] for ind in [3,4]],
            "muR": ['%sgen%i'%(sig,ind) for sig in ['tbart','tW'] for ind in [5,8]],
            "tot": ['%sgen%i'%(sig,ind) for sig in ['tbart','tW'] for ind in [6,10]]
            }
    tWinterf=['tWDS']

    systSignalList=Mtop+ttParton_tt+ttParton_tW+tWinterf+ME["muF"]+ME["muR"]+ME["tot"]

    MtopMap={}
    ttPartonMap={}
    tWinterfMap={}
    MEMap={
            "muF" : {},
            "muR" : {},
            "tot" : {}
            }
    for wid in modWidList :
        MtopMap[    'tbart%s'%wid]=['tbartm=169.5%s'  %(wid),'tbartm=175.5%s'%(wid)]
        MtopMap[    'tW%s'   %wid]=['tWm=169.5%s'     %(wid),'tWm=175.5%s'   %(wid)]

        ttPartonMap['tbart%s'%wid]=['tbartscaledown%s'%(wid),'tbartscaleup%s'%(wid)]
        ttPartonMap['tW%s'   %wid]=['tWscaledown%s'   %(wid),'tWscaleup%s'   %(wid)]

        tWinterfMap['tW%s'   %wid]=['tWDS%s'   %(wid)]

        MEMap["muF"]['tbart%s'%wid]=['tbartgen3%s'%(wid),'tbartgen4%s' %(wid)]
        MEMap["muR"]['tbart%s'%wid]=['tbartgen5%s'%(wid),'tbartgen8%s' %(wid)]
        MEMap["tot"]['tbart%s'%wid]=['tbartgen6%s'%(wid),'tbartgen10%s'%(wid)]

        MEMap["muF"]['tW%s'%wid]=['tWgen3%s'%(wid),'tWgen4%s' %(wid)]
        MEMap["muR"]['tW%s'%wid]=['tWgen5%s'%(wid),'tWgen8%s' %(wid)]
        MEMap["tot"]['tW%s'%wid]=['tWgen6%s'%(wid),'tWgen10%s'%(wid)]


    sampleSysts=[
          #ttbar modelling
          ('Mtop'          , MtopMap    , True , True, False),
          ('ttPartonShower', ttPartonMap, False, True, False),
          #tWinterference
          ('tWttinterf'    , tWinterfMap, False, True, True) TODO
          #ME generator
          ('MEmuF'         , MEMap["muF"], False, True, False),
          ('MEmuR'         , MEMap["muR"], False, True, False),
          ('MEtot'         , MEMap["tot"], False, True, False)
    ]


    genSysts=[
        ('jes',   False,False,False),
        ('les',   False,False,False),
        ('ltag',  False,False,False),
        ('trig',  False,False,False),
        ('sel',   False,False,False),
        ('toppt', False,False,False),
        ('jer',   False,False,False),
        ('btag',  False,False,False),
        ('pu',     True,False,False)
    ]

    # prepare output directory
    os.system('mkdir -p %s'%opt.output)

    anCat=''
    for subDir in opt.input.split('/'):
        if 'analysis_' not in subDir: continue
        anCat=subDir.replace('analysis_','')

    # get data and nominal expectations
    fIn=ROOT.TFile.Open(opt.input)
    systfIn=None
    if opt.systInput:
        systfIn=ROOT.TFile.Open(opt.systInput)

    # prepare output ROOT file
    if not opt.skipMakingShapes :
        outFile='%s/shapes.root'%(opt.output)
        fOut=ROOT.TFile.Open(outFile,'RECREATE')
        fOut.Close()

    # keep track of progress
    cardIndex=-1
    numCards =(len(rawWidList)-1)*len(lfsList)*len(lbCatList)*len(catList)*len(distList)

    #loop over lepton final states
    for (lbCat,lfs,cat,dist) in [(a,b,c,d) for a in lbCatList
            for b in lfsList
            for c in catList
            for d in distList] :
        if opt.skipMakingShapes : break


        obs=ROOT.TH1F('','',100,0,100)
        exp={}
        #nominal expectations
        if opt.addSigs :
            obs,exp=getMergedDists(fIn,('%s%s%s_%s_'%(lbCat,lfs,cat,dist)),rawSignalList,'top',widList,nomWid,signalList)
        else :
            obs,exp=getMergedDists(fIn,('%s%s%s_%s_'%(lbCat,lfs,cat,dist)),None,'',widList,nomWid,signalList)

        if not opt.truthDataset=="" :
            obs=makeMCTruthHist(opt.truthDataset,signalList,exp)
        #exp=filterShapeList(exp,signalList,rawSignalList)

        nomShapes=exp.copy()
        nomShapes['data_obs']=obs
        saveToShapesFile(outFile,nomShapes,('%s%s%s_%s'%(lbCat,lfs,cat,dist)))

        #loop over categories, widths
        for wid in modWidList:
            if modNomWid in wid : continue

            cardIndex+=1
            print 'Initiating %s datacard for %s%s%s_%s \t\t [%i/%i]'%(dist,lbCat,lfs,cat,wid,cardIndex,numCards)


            #start the datacard
            datacard=open('%s/datacard__%s_%s%s%s_%s.dat'%(opt.output,wid,lbCat,lfs,cat,dist),'w')
            datacard.write('#\n')
            datacard.write('# Generated by %s with git hash %s for analysis category %s%s%s_%s\n' % (getpass.getuser(),
                commands.getstatusoutput('git log --pretty=format:\'%h\' -n 1')[1],
                lbCat, lfs, cat, wid) )

            datacard.write('#\n')
            datacard.write('imax *\n')
            datacard.write('jmax *\n')
            datacard.write('kmax *\n')
            datacard.write('-'*50+'\n')
            datacard.write('shapes *        * shapes.root %s%s%s_%s/$PROCESS %s%s%s_%s_$SYSTEMATIC/$PROCESS\n'%(lbCat,lfs,cat,dist,lbCat,lfs,cat,dist))
            datacard.write('-'*50+'\n')
            datacard.write('bin 1\n')
            datacard.write('observation %3.1f\n' % obs.Integral())
            datacard.write('-'*50+'\n')

            #expectations
            datacard.write('\t\t\t %32s'%'bin')
            for i in xrange(0,len(exp)+(2 if opt.addSigs else 0)-(len(modWidList)-1)*len(signalList)+len(signalList)):
                datacard.write('%15s'%'1')
            datacard.write('\n')
            datacard.write('\t\t\t %32s'%'process')
            for sig in signalList: datacard.write('%15s'%('%s%s'%(sig,modNomWid)))
            for sig in signalList: datacard.write('%15s'%('%s%s'%(sig,wid)))
            for proc in exp:
                isSig=False
                for sig in modWidList :
                    if sig in proc : isSig=True
                if isSig : continue
                datacard.write('%15s'%proc)
            datacard.write('\n')
            datacard.write('\t\t\t %32s'%'process')
            for i in xrange(0,2*len(signalList)) : datacard.write('%15s'%str(i+1-2*len(signalList)))
            i=0
            for proc in exp:
                isSig=False
                for sig in modWidList :
                    if sig in proc : isSig=True
                if isSig : continue
                i=i+1
                datacard.write('%15s'%str(i))
            datacard.write('\n')
            datacard.write('\t\t\t %32s'%'rate')
            for sig in signalList :
                datacard.write('%15s'%('%3.2f'%(exp['%s%s'%(sig,modNomWid)].Integral())))
            for sig in signalList :
                datacard.write('%15s'%('%3.2f'%(exp['%s%s'%(sig,wid)].Integral())))
            for proc in exp:
                isSig=False
                for sig in modWidList :
                    if sig in proc : isSig=True
                if isSig : continue
                datacard.write('%15s'%('%3.2f'%exp[proc].Integral()))
            datacard.write('\n')
            datacard.write('-'*50+'\n')


            #rate systematics
            try:
                jetCat=cat[:-2] if cat.endswith('t') else cat
                rateSysts.append( ('MultiJetsNorm%s%s'%(jetCat,anCat),  1+qcdNorm[jetCat][1],                       'lnN',    ['Multijetsdata']    ,[]) )
            except:
                pass

            for syst,val,pdf,whiteList,blackList in rateSysts:

                datacard.write('%32s %8s'%(syst,pdf))
                entryTxt=''
                try:
                    entryTxt='%15s'%('%3.3f/%3.3f'%(ROOT.TMath.Max(val[0],0.01),val[1]))
                except:
                    entryTxt='%15s'%('%3.3f'%val)

                for sig in signalList:
                    newSig='%s%s'%(sig,modNomWid)
                    if (len(whiteList)==0 and not newSig in blackList) or newSig in whiteList:
                        datacard.write(entryTxt)
                    else:
                        datacard.write('%15s'%'-')
                for sig in signalList:
                    newSig='%s%s'%(sig,wid)
                    if (len(whiteList)==0 and not newSig in blackList) or newSig in whiteList:
                        datacard.write(entryTxt)
                    else:
                        datacard.write('%15s'%'-')
                for proc in exp:
                    isSig=False
                    for sig in modWidList :
                        if sig in proc : isSig=True
                    if isSig : continue
                    if (len(whiteList)==0 and not proc in blackList) or proc in whiteList:
                        datacard.write(entryTxt)
                    else:
                        datacard.write('%15s'%'-')
                datacard.write('\n')

            #generator level systematics
            if systfIn is None :
                datacard.close()
                continue


            # sample systematics
            _,genVarShapes = getMergedDists(fIn,
                    ('%s%s%s_%s_'%(lbCat,lfs,cat,dist)),
                    (rawSignalList if opt.addSigs else None),
                    ('top' if opt.addSigs else ''),
                    widList,nomWid,systSignalList)
            _,altExp       = getMergedDists(systfIn,
                    ('%s%s%s_%s_'%(lbCat,lfs,cat,dist)),
                    (rawSignalList if opt.addSigs else None),
                    ('top' if opt.addSigs else ''),
                    widList,nomWid,systSignalList)

            for systVar, procsToApply, normalize, useAltShape, projectRelToNom in sampleSysts:

                #prepare shapes and check if variation is significant
                downShapes, upShapes = {}, {}

                for iproc in procsToApply:
                    nomH=exp[iproc]

                    #check which shape to use
                    if useAltShape:

                        #get directly from another file
                        downH  = altExp[ procsToApply[iproc][0] ]
                        if len( procsToApply[iproc] ) > 1 :
                            upH    = altExp[ procsToApply[iproc][1] ]
                        else:
                            #if only one variation is available, mirror it
                            upH = downH.Clone( '%s%sUp'%(iproc,systVar) )
                            for xbin in xrange(1,upH.GetNbinsX()+1):
                                diff=upH.GetBinContent(xbin)-nomH.GetBinContent(xbin)
                                upH.SetBinContent(xbin,nomH.GetBinContent(xbin)-diff)
                    else:

                        #project from 2D histo (re-weighted from nominal sample)
                        ybinUp, ybinDown = -1, -1
                        for ybin in xrange(1,genVarShapes[ iproc ].GetNbinsY()+1):
                            label = genVarShapes[ iproc ].GetYaxis().GetBinLabel(ybin)
                            if procsToApply[iproc][0] in label : ybinDown=ybin
                            if procsToApply[iproc][1] in label : ybinUp=ybin

                        downH = genVarShapes[ iproc ].ProjectionX('%s%sDown'%(iproc,systVar), ybinDown, ybinDown)
                        upH   = genVarShapes[ iproc ].ProjectionX('%s%sUp'%(iproc,systVar),   ybinUp,   ybinUp)

                    # use do down/up x nom to generate the variation, then mirror it
                    if projectRelToNom:
                        ratioH=downH.Clone()
                        ratioH.Divide(upH)
                        for xbin in xrange(1,nomH.GetNbinsX()+1):
                            nomVal=nomH.GetBinContent(xbin)
                            varVal = ratioH.GetBinContent(xbin) * nomVal
                            upH.SetBinContent(xbin, varVal)
                            varVal = varVal- nomVal
                            downH.SetBinContent(xbin, nomVal-varVal)

                    #normalize (shape only variation is considered)
                    if normalize : downH.Scale( nomH.Integral()/downH.Integral() )
                    if normalize : upH.Scale( nomH.Integral()/upH.Integral() )

                    #check if variation is meaningful
                    accept = acceptVariationForDataCard(nomH=nomH, upH=upH, downH=downH)
                    if not accept : continue

                    #save
                    downShapes[iproc]=downH
                    upShapes[iproc]=upH

                #check if something has been accepted
                if len(upShapes)==0 : continue

                #export to shapes file
                saveToShapesFile(outFile,downShapes,lbCat+lfs+cat+"_"+dist+"_"+systVar+'Down')
                saveToShapesFile(outFile,upShapes,lbCat+lfs+cat+"_"+dist+"_"+systVar+'Up')

                #write to datacard
                datacard.write('%26s shape'%systVar)
                for sig in signalList:
                    if ("%s%s"%(sig,wid)) in procsToApply and ("%s%s"%(sig,wid)) in upShapes:
                        datacard.write('%15s'%'1')
                    else:
                        datacard.write('%15s'%'-')
                for sig in signalList:
                    if ("%s%s"%(sig,wid)) in procsToApply and ("%s%s"%(sig,wid)) in upShapes:
                        datacard.write('%15s'%'1')
                    else:
                        datacard.write('%15s'%'-')
                for proc in exp:
                    isSig=False
                    for sig in modWidList :
                        if sig in proc : isSig=True
                    if isSig : continue
                    if proc in procsToApply and proc in upShapes:
                        datacard.write('%15s'%'1')
                    else:
                        datacard.write('%15s'%'-')
                datacard.write('\n')


            #
            for systVar, normalize, useAltShape, projectRelToNom in genSysts:
                _,genVarShapesUp = getMergedDists((systfIn if useAltShape else fIn),
                        ('%sup%s%s%s_%s_'%(systVar,lbCat,lfs,cat,dist)),
                        (rawSignalList if opt.addSigs else None),
                        ('top' if opt.addSigs else ''),
                        widList,nomWid,signalList)
                _,genVarShapesDn = getMergedDists((systfIn if useAltShape else fIn),
                        ('%sdn%s%s%s_%s_'%(systVar,lbCat,lfs,cat,dist)),
                        (rawSignalList if opt.addSigs else None),
                        ('top' if opt.addSigs else ''),
                        widList,nomWid,signalList)

                #prepare shapes and check if variation is significant
                downShapes, upShapes = {}, {}

                for iproc in exp:
                    nomH=exp[iproc]

                    if not iproc in genVarShapesDn :
                        continue
                    #get directly from another file
                    downH  = genVarShapesDn[iproc]
                    if iproc in genVarShapesUp:
                        upH = genVarShapesUp[iproc]
                    else:
                        #if only one variation is available, mirror it
                        upH = downH.Clone( '%s%sUp'%(iproc,systVar) )
                        for xbin in xrange(1,upH.GetNbinsX()+1):
                            diff=upH.GetBinContent(xbin)-nomH.GetBinContent(xbin)
                            upH.SetBinContent(xbin,nomH.GetBinContent(xbin)-diff)

                    # use do down/up x nom to generate the variation, then mirror it
                    if projectRelToNom:
                        ratioH=downH.Clone()
                        ratioH.Divide(upH)
                        for xbin in xrange(1,nomH.GetNbinsX()+1):
                            nomVal=nomH.GetBinContent(xbin)
                            varVal = ratioH.GetBinContent(xbin) * nomVal
                            upH.SetBinContent(xbin, varVal)
                            varVal = varVal- nomVal
                            downH.SetBinContent(xbin, nomVal-varVal)

                    #normalize (shape only variation is considered)
                    if normalize : downH.Scale( nomH.Integral()/downH.Integral() )
                    if normalize : upH.Scale( nomH.Integral()/upH.Integral() )

                    #check if variation is meaningful
                    accept = acceptVariationForDataCard(nomH=nomH, upH=upH, downH=downH)
                    if not accept : continue

                    #save
                    downShapes[iproc]=downH
                    upShapes[iproc]=upH

                #check if something has been accepted
                if len(upShapes)==0 : continue

                #export to shapes file
                saveToShapesFile(outFile,downShapes,lbCat+lfs+cat+"_"+dist+"_"+systVar+'Down')
                saveToShapesFile(outFile,upShapes,lbCat+lfs+cat+"_"+dist+"_"+systVar+'Up')

                #write to datacard
                datacard.write('%26s shape'%systVar)
                for sig in signalList:
                    if ("%s%s"%(sig,modNomWid)) in exp and ("%s%s"%(sig,modNomWid)) in upShapes:
                        datacard.write('%15s'%'1')
                    else:
                        datacard.write('%15s'%'-')
                for sig in signalList:
                    if ("%s%s"%(sig,wid)) in exp and ("%s%s"%(sig,wid)) in upShapes:
                        datacard.write('%15s'%'1')
                    else:
                        datacard.write('%15s'%'-')
                for proc in exp:
                    isSig=False
                    for sig in modWidList :
                        if sig in proc : isSig=True
                    if isSig : continue
                    if proc in exp and proc in upShapes:
                        datacard.write('%15s'%'1')
                    else:
                        datacard.write('%15s'%'-')
                datacard.write('\n')

        #all done
        datacard.close()

    ##################
    # BEGIN MORPHING #
    ##################

    if systfIn is None : return
    if opt.skipMorphing : return

    import CMS_lumi
    import tdrStyle
    import numpy
    tdrStyle.setTDRStyle()

    print "\n Creating morphed dists\n"

    kOrangeList=[-4,-2,0,1,-3,7,8,10,9,2]
    widths=map(float,[wid.replace('p','.').replace('w','') for wid in rawWidList])
    massInfo=[(169.5,opt.systInput,'t#bar{t} m=169.5'),
              (172.5,opt.input    ,'t#bar{t}'),
              (175.5,opt.systInput,'t#bar{t} m=175.5'),
              (169.5,opt.systInput,'tW m=169.5'),
              (172.5,opt.input    ,'tW'),
              (175.5,opt.systInput,'tW m=175.5')]
    minMT=169.5
    nomMT=172.5
    maxMT=175.5
    minGammaT=0.5*1.324
    nomGammaT=1.324
    maxGammaT=5.0*1.324
    distToTitle={
            "mlb":    "Inclusive M_{lb}",
            "minmlb": "Minimum M_{lb}",
            "mdrmlb": "#DeltaR-Filtered M_{lb}",
            "incmlb": "Inclusive M_{lb}",
            "sncmlb": "Semi-Inclusive M_{lb}",
            "mt2mlb": "M_{T2}^{lb} Strategy"
           }

    canvas=ROOT.TCanvas()

    # make workspace for each signal process
    first=True
    for sig,dist,lbCat,ch,cat in [(a,b,c,d,e)
            for a in signalList
            for b in distList
            for c in (['highpt'] if not opt.allMorphs else lbCatList)
            for d in (['EM'] if not opt.allMorphs else lfsList)
            for e in (['2b'] if not opt.allMorphs else catList)]:
        modSig=replaceBadCharacters(sig)
        distTitle="M_{lb}" if dist not in distToTitle else distToTitle[dist]

        # get the proper mass information for this signal
        masses=[]
        for mass,fname,distname in massInfo :
            if modSig in replaceBadCharacters(distname) :
                masses += [(mass,fname,distname)]

        # create workspace
        ws=ROOT.RooWorkspace('sigws_%s%s%s_%s_%s'%(lbCat,ch,cat,modSig,dist))
        ws.factory('x[0,300]')

        ##########################################
        # produce systematic uncertainties in ws #
        ##########################################
        downShapes, upShapes = {}, {}

        #nominal expectations
        exp={}
        if opt.addSigs :
            _,exp=getMergedDists(fIn,('%s%s%s_%s_'%(lbCat,ch,cat,dist)),rawSignalList,'top',widList,nomWid,signalList)
        else :
            _,exp=getMergedDists(fIn,('%s%s%s_%s_'%(lbCat,ch,cat,dist)),None,'',widList,nomWid,signalList)

        # sample systematics
        _,genVarShapes = getMergedDists(fIn,
                ('%s%s%s_%s_'%(lbCat,ch,cat,dist)),
                (rawSignalList if opt.addSigs else None),
                ('top' if opt.addSigs else ''),
                widList,nomWid,systSignalList)
        _,altExp       = getMergedDists(systfIn,
                ('%s%s%s_%s_'%(lbCat,ch,cat,dist)),
                (rawSignalList if opt.addSigs else None),
                ('top' if opt.addSigs else ''),
                widList,nomWid,systSignalList)

        for systVar, procsToApply, normalize, useAltShape, projectRelToNom in sampleSysts:
            downShapes[systVar]={}
            upShapes[systVar]={}

            for iproc in procsToApply:
                if sig not in iproc : continue
                nomH=exp[iproc]

                #check which shape to use
                if useAltShape:

                    #get directly from another file
                    downH  = altExp[ procsToApply[iproc][0] ]
                    if len( procsToApply[iproc] ) > 1 :
                        upH    = altExp[ procsToApply[iproc][1] ]
                    else:
                        #if only one variation is available, mirror it
                        upH = downH.Clone( '%s%sUp'%(iproc,systVar) )
                        for xbin in xrange(1,upH.GetNbinsX()+1):
                            diff=upH.GetBinContent(xbin)-nomH.GetBinContent(xbin)
                            upH.SetBinContent(xbin,nomH.GetBinContent(xbin)-diff)
                else:

                    #project from 2D histo (re-weighted from nominal sample)
                    ybinUp, ybinDown = -1, -1
                    for ybin in xrange(1,genVarShapes[ iproc ].GetNbinsY()+1):
                        label = genVarShapes[ iproc ].GetYaxis().GetBinLabel(ybin)
                        if procsToApply[iproc][0] in label : ybinDown=ybin
                        if procsToApply[iproc][1] in label : ybinUp=ybin

                    downH = genVarShapes[ iproc ].ProjectionX('%s%sDown'%(iproc,systVar), ybinDown, ybinDown)
                    upH   = genVarShapes[ iproc ].ProjectionX('%s%sUp'%(iproc,systVar),   ybinUp,   ybinUp)

                # use do down/up x nom to generate the variation, then mirror it
                if projectRelToNom:
                    ratioH=downH.Clone()
                    ratioH.Divide(upH)
                    for xbin in xrange(1,nomH.GetNbinsX()+1):
                        nomVal=nomH.GetBinContent(xbin)
                        varVal = ratioH.GetBinContent(xbin) * nomVal
                        upH.SetBinContent(xbin, varVal)
                        varVal = varVal- nomVal
                        downH.SetBinContent(xbin, nomVal-varVal)

                #normalize (shape only variation is considered)
                if normalize : downH.Scale( nomH.Integral()/downH.Integral() )
                if normalize : upH.Scale( nomH.Integral()/upH.Integral() )

                #check if variation is meaningful
                accept = acceptVariationForDataCard(nomH=nomH, upH=upH, downH=downH)
                if not accept : continue

                #save
                downShapes[systVar][iproc]=downH
                upShapes[systVar][iproc]=upH


        for systVar, normalize, useAltShape, projectRelToNom in genSysts:
            _,genVarShapesUp = getMergedDists((systfIn if useAltShape else fIn),
                    ('%sup%s%s%s_%s_'%(systVar,lbCat,ch,cat,dist)),
                    (rawSignalList if opt.addSigs else None),
                    ('top' if opt.addSigs else ''),
                    widList,nomWid,signalList)
            _,genVarShapesDn = getMergedDists((systfIn if useAltShape else fIn),
                    ('%sdn%s%s%s_%s_'%(systVar,lbCat,ch,cat,dist)),
                    (rawSignalList if opt.addSigs else None),
                    ('top' if opt.addSigs else ''),
                    widList,nomWid,signalList)

            downShapes[systVar]={}
            upShapes[systVar]={}

            for iproc in exp:
                if sig not in iproc : continue
                nomH=exp[iproc]

                if not iproc in genVarShapesDn :
                    continue
                #get directly from another file
                downH  = genVarShapesDn[iproc]
                if iproc in genVarShapesUp:
                    upH = genVarShapesUp[iproc]
                else:
                    #if only one variation is available, mirror it
                    upH = downH.Clone( '%s%sUp'%(iproc,systVar) )
                    for xbin in xrange(1,upH.GetNbinsX()+1):
                        diff=upH.GetBinContent(xbin)-nomH.GetBinContent(xbin)
                        upH.SetBinContent(xbin,nomH.GetBinContent(xbin)-diff)

                # use do down/up x nom to generate the variation, then mirror it
                if projectRelToNom:
                    ratioH=downH.Clone()
                    ratioH.Divide(upH)
                    for xbin in xrange(1,nomH.GetNbinsX()+1):
                        nomVal=nomH.GetBinContent(xbin)
                        varVal = ratioH.GetBinContent(xbin) * nomVal
                        upH.SetBinContent(xbin, varVal)
                        varVal = varVal- nomVal
                        downH.SetBinContent(xbin, nomVal-varVal)

                #normalize (shape only variation is considered)
                if normalize : downH.Scale( nomH.Integral()/downH.Integral() )
                if normalize : upH.Scale( nomH.Integral()/upH.Integral() )

                #check if variation is meaningful
                accept = acceptVariationForDataCard(nomH=nomH, upH=upH, downH=downH)
                if not accept : continue

                #save
                downShapes[systVar][iproc]=downH
                upShapes[systVar][iproc]=upH


        ######################
        # Produce morph grid #
        ######################

        # initialize grid with width and mass
        widthDim=ROOT.RooBinning(len(widths),0,len(widths)-1)
        massDim =ROOT.RooBinning(len(masses),0,len(masses)-1)
        refGrid =ROOT.RooMomentMorphND.Grid(widthDim,massDim)

        # add systematics binnings to grid
        for systVar in upShapes :
            if len(upShapes[systVar])==0 : continue
            binning=ROOT.RooBinning(3,-1,1)
            refGrid.addBinning(binning)

        massAxes=[ws.var('x').frame()]*len(widths)
        widAxes =[ws.var('x').frame()]*len(masses)
        for imass in xrange(0,len(masses)):
            mass,url,proc=masses[imass]

            if modSig not in replaceBadCharacters(proc) : continue

            tfIn=ROOT.TFile.Open(url)
            for iwid in xrange(0,len(widths)):

                #get histogram and convert to a PDF
                dirname='%s%s%s_%s_%3.1fw'%(lbCat,ch,cat,dist,widths[iwid])
                h=tfIn.Get(dirname+"/"+dirname+'_'+proc)
                name='%s_m%d'%(dirname,int(10*mass))
                data=ROOT.RooDataHist(name,name,ROOT.RooArgList(ws.var("x")),h)
                pdf=ROOT.RooHistPdf(name+"_pdf",name+"_pdf",ROOT.RooArgSet(ws.var("x")),data)
                pdf.plotOn(massAxes[iwid],
                        ROOT.RooFit.Name("%3.1f"%mass),
                        ROOT.RooFit.LineColor(ROOT.kOrange+kOrangeList[imass*3]))
                pdf.plotOn(widAxes[imass],
                        ROOT.RooFit.Name("%3.1f"%widths[iwid]),
                        ROOT.RooFit.LineColor(ROOT.kOrange+kOrangeList[iwid]))
                getattr(ws,'import')(pdf,ROOT.RooCmdArg())

                #add pdf to the grid
                print 'Adding',pdf.GetName(),'@ (',iwid,',',imass,')'
                insertVector=numpy.zeros(2+len(upShapes))
                insertVector[0]=iwid
                insertVector[1]=imass
                refGrid.addPdf(ws.pdf(pdf.GetName()),2+len(upShapes),insertVector)

                isyst=0
                for proc in upShapes :
                    # get systematic histos
                    systHUp=None
                    systHDn=None
                    for sigwid in upShapes[proc] :
                        if ("%3.1f"%(widths[iwid])).replace('.','p') in sigwid :
                            systHUp=  upShapes[proc][sigwid]
                            systHDn=downShapes[proc][sigwid]
                            break
                    if systHUp is None or systHDn is None: continue

                    # make up RooAbsPdf
                    upName='%s_m%d_%sUp'%(dirname,int(10*mass),proc)
                    upData=ROOT.RooDataHist(upName,upName,ROOT.RooArgList(ws.var("x")),systHUp)
                    upPdf=ROOT.RooHistPdf(upName+"_pdf",upName+"_pdf",ROOT.RooArgSet(ws.var("x")),upData)
                    getattr(ws,'import')(upPdf,ROOT.RooCmdArg())

                    # make down RooAbsPdf
                    dnName='%s_m%d_%sDown'%(dirname,int(10*mass),proc)
                    dnData=ROOT.RooDataHist(dnName,dnName,ROOT.RooArgList(ws.var("x")),systHDn)
                    dnPdf=ROOT.RooHistPdf(dnName+"_pdf",dnName+"_pdf",ROOT.RooArgSet(ws.var("x")),dnData)
                    getattr(ws,'import')(dnPdf,ROOT.RooCmdArg())

                    insertVector=numpy.zeros(2+len(upShapes))
                    insertVector[0]=iwid
                    insertVector[1]=imass

                    # add pdfs to grid, setting all other systs to nominal
                    insertVector[2+isyst]=1
                    refGrid.addPdf(ws.pdf(upPdf.GetName()),2+len(upShapes),insertVector)
                    insertVector[2+isyst]=-1
                    refGrid.addPdf(ws.pdf(dnPdf.GetName()),2+len(upShapes),insertVector)
                    isyst+=1

            tfIn.Close()

        ###############################
        # create input PDF validation #
        ###############################
        # all masses for one width
        for i in range(0,len(massAxes)) :
            if opt.noValidation : break
            canvas.cd()
            canvas.SetLogy()

            massAxes[i].GetXaxis().SetTitle("%s [GeV]"%distTitle)
            massAxes[i].GetYaxis().SetTitle("Probability density: lepton-jet pairs")
            massAxes[i].SetTitle("")
            massAxes[i].SetLineWidth(1)
            massAxes[i].Draw()

            leg=ROOT.TLegend(0.65,0.17,0.90,0.37)
            leg.SetHeader("#Gamma_{t} = %s#times#Gamma_{SM}"%rawWidList[i])
            for mass,_,_ in masses :
                leg.AddEntry("%3.1f"%(mass),"m_{t} = %3.1f GeV"%(mass),"L")
            leg.Draw()

            CMS_lumi.relPosX = 0.180
            CMS_lumi.extraText = "Simulation Preliminary"
            CMS_lumi.extraOverCmsTextSize=0.50
            CMS_lumi.lumiTextSize = 0.55
            CMS_lumi.CMS_lumi(canvas,4,0)
            canvas.Update()
            canvas.SaveAs("%s/massInputValidation_%s%s%s_%s_%s.pdf"%(opt.output,lbCat,ch,cat,dist,modWidList[i]))
            canvas.SetGrayscale(True)
            canvas.Update()
            canvas.SaveAs("%s/gScale__massInputValidation_%s%s%s_%s_%s.pdf"%(opt.output,lbCat,ch,cat,dist,modWidList[i]))
            canvas.SetGrayscale(False)

        # all widths for one mass
        canvas.clear()
        for i in range(0,len(widAxes)) :
            if opt.noValidation : break
            canvas.cd()
            canvas.SetLogy()

            widAxes[i].GetXaxis().SetTitle("%s [GeV]"%distTitle)
            widAxes[i].GetYaxis().SetTitle("Probability density: lepton-jet pairs")
            widAxes[i].SetTitle("")
            widAxes[i].SetLineWidth(1)
            widAxes[i].Draw()

            leg=ROOT.TLegend(0.65,0.17,0.90,0.37)
            leg.SetHeader("m_{t} = %3.1f GeV"%masses[i][0])
            for wid in widths :
                leg.AddEntry("%3.1f"%(wid),"#Gamma_{t} = %3.1f#times#Gamma_{SM}"%(wid),"L")
            leg.Draw()

            CMS_lumi.relPosX = 0.180
            CMS_lumi.extraText = "Simulation Preliminary"
            CMS_lumi.extraOverCmsTextSize=0.50
            CMS_lumi.lumiTextSize = 0.55
            CMS_lumi.CMS_lumi(canvas,4,0)
            canvas.Update()
            canvas.SaveAs("%s/widthInputValidation_%s%s%s_%s_%s.pdf"%(opt.output,lbCat,ch,cat,dist,("3.1f"%masses[i][0]).replace('.','p')))
            canvas.SetGrayscale(True)
            canvas.Update()
            canvas.SaveAs("%s/gScale__widthInputValidation_%s%s%s_%s_%s.pdf"%(opt.output,lbCat,ch,cat,dist,("3.1f"%masses[i][0]).replace('.','p')))
            canvas.SetGrayscale(False)

        #################################
        # create pdf and save workspace #
        #################################
        ws.factory('alpha[%i,%i]'%(0,len(widths)-1))
        ws.factory('beta[%i,%i]'%(0,len(masses)-1))
        pdf=ROOT.RooMomentMorphND('widmorphpdf','widmorphpdf',
                                  ROOT.RooArgList( ws.var('alpha'), ws.var('beta') ),
                                  ROOT.RooArgList( ws.var('x') ),
                                  refGrid,
                                  ROOT.RooMomentMorphND.Linear)
        pdf.useHorizontalMorphing(False)
        getattr(ws,'import')(pdf,ROOT.RooCmdArg())

        # save workspace to shapes
        outFile='%s/shapes.root'%(opt.output)
        fOut=ROOT.TFile.Open(outFile,'UPDATE')
        fOut.cd()
        ws.Write()
        fOut.Close()


        ###############################
        # Produce morphing animations #
        ###############################
        if not opt.allMorphs and not first : continue
        if opt.noValidation : continue
        ROOT.gStyle.SetOptStat(0)
        status=ROOT.TLatex()

        zLimList={ "mlb": 3.5e-04,
                "asens" : 3.5e-04,
                "bsens" : 3.5e-04 }
        n2DScan=60
        n3DScan=120

        from PIL import Image, ImageSequence
        from images2gif import writeGif

        # setup morph validation arrays
        rotScanAlphaImgs  = []
        rotScanBetaImgs   = []
        alphaScanImgs     = []
        betaScanImgs      = []
        sensAlphaScanImgs = []
        sensBetaScanImgs  = []

        os.mkdir('%s/gifplots_%s%s%s_%s_%s'%(opt.output,lbCat,ch,cat,sig,dist))

        # NOTE: we want to reopen the outfile so that we see what Combine sees.
        #       This is inefficient but it is important validation!
        fOut=ROOT.TFile.Open(outFile)
        workspace=fOut.Get("sigws_%s%s%s_%s_%s"%(lbCat,ch,cat,modSig,dist))
        morphPDF= workspace.pdf("widmorphpdf")

        alphaVar= workspace.var("alpha")
        betaVar = workspace.var("beta")
        mlbVar  = workspace.var("x")

        # this is used separately, so we can use pdf
        dMorDAlpha=pdf.derivative(alphaVar)
        dMorDBeta =pdf.derivative(betaVar)
        dMorDMlb  =pdf.derivative(mlbVar)

        #import pdb
        #pdb.set_trace()

        #################################
        # create morphed PDF validation #
        #################################
        histos=[mlbVar.frame()]*len(widths)
        for i in range(0,len(widths)) :
            alphaVar.setVal(widths[i])

            leg=ROOT.TLegend(0.65,0.17,0.90,0.37)
            leg.SetHeader("#Gamma_{t} = %s#times#Gamma_{SM}"%rawWidList[i])

            for imass in range(0,len(masses)) :
                betaVar.setVal(imass)
                morphPDF.plotOn(histos[i],
                        ROOT.RooFit.Name("%3.1f"%masses[imass][0]),
                        ROOT.RooFit.LineColor(ROOT.kOrange+kOrangeList[imass*3]))
                leg.AddEntry("%3.1f"%(masses[imass][0]),"m_{t} = %3.1f GeV"%(masses[imass][0]),"L")

            histos[i].GetXaxis().SetTitle("%s [GeV]"%distTitle)
            histos[i].GetYaxis().SetTitle("Morphed density: lepton-jet pairs")
            histos[i].SetTitle("")
            histos[i].SetLineWidth(1)
            histos[i].Draw()
            leg.Draw()

            CMS_lumi.relPosX = 0.180
            CMS_lumi.extraText = "Simulation Preliminary"
            CMS_lumi.extraOverCmsTextSize=0.50
            CMS_lumi.lumiTextSize = 0.55
            CMS_lumi.CMS_lumi(canvas,4,0)

            canvas.SetLogy()
            canvas.Update()
            canvas.SaveAs("%s/morphValidation_%s%s%s_%s_%s.pdf"%(opt.output,lbCat,ch,cat,dist,modWidList[i]))
            canvas.SetGrayscale(True)
            canvas.Update()
            canvas.SaveAs("%s/gScale__morphValidation_%s%s%s_%s_%s.pdf"%(opt.output,lbCat,ch,cat,dist,modWidList[i]))
            canvas.SetGrayscale(False)

        ##########################################
        # create 3D plots that rotate the camera #
        ##########################################
        canvas.SetLogx(False)
        canvas.SetLogy(False)
        canvas.SetLogz(True)
        ROOT.gStyle.SetPalette(52)

        histAlpha = mlbVar.createHistogram("Morphing against width variations",alphaVar)
        morphPDF.fillHistogram(histAlpha,ROOT.RooArgList(mlbVar,alphaVar))
        histAlpha.GetYaxis().SetTitleOffset(1.1)
        histAlpha.GetYaxis().SetTitle("Grid width index")
        histAlpha.GetXaxis().SetTitleOffset(1.35)
        histAlpha.GetXaxis().SetTitle("%s [GeV]"%distTitle)
        histAlpha.SetTitle("")

        histBeta  = mlbVar.createHistogram("Morphing against mass variations",betaVar)
        morphPDF.fillHistogram(histBeta ,ROOT.RooArgList(mlbVar,betaVar))
        histBeta.GetYaxis().SetTitleOffset(1.1)
        histBeta.GetYaxis().SetTitle("Grid mass index")
        histBeta.GetXaxis().SetTitleOffset(1.35)
        histBeta.GetXaxis().SetTitle("%s [GeV]"%distTitle)
        histBeta.SetTitle("")

        CMS_lumi.relPosX = 0.180
        CMS_lumi.cmsTextOffset=0
        CMS_lumi.extraText = "Simulation Preliminary"
        CMS_lumi.extraOverCmsTextSize=0.50
        CMS_lumi.lumiTextSize = 0.55

        alphaVar.setVal(1)
        betaVar.setVal(1)

        for theta in xrange(0,359,int(360/n3DScan)) :
            # mlb vs. mass plot for 3D scan
            if theta == 0 : zLimList["mlb"]=histAlpha.GetMaximum()*1.1
            histAlpha.SetMaximum(zLimList["mlb"])
            histAlpha.Draw("SURF1")
            status.DrawLatexNDC(0.75,0.02,"m_{t}=%3.2f GeV"%(betaVar.getVal()*(maxMT-minMT)/betaVar.getMax()+minMT))
            ROOT.gPad.SetPhi(theta)

            CMS_lumi.CMS_lumi(canvas,4,0)
            if first:
                canvas.SetLeftMargin(canvas.GetRightMargin()*1.1)

            canvas.SaveAs("%s/gifplots_%s_%s/rotscanalpha_%s_%i.png"%(opt.output,sig,dist,sig,theta))
            canvas.Clear()

            # mlb vs. width plot for 3D scan
            histBeta.SetMaximum(zLimList["mlb"])
            histBeta.Draw("SURF1")
            status.DrawLatexNDC(0.75,0.02,"#Gamma_{t}=%3.2f GeV"%(alphaVar.getVal()*(maxGammaT-minGammaT)/alphaVar.getMax()+minGammaT))
            ROOT.gPad.SetPhi(theta)

            CMS_lumi.CMS_lumi(canvas,4,0)
            if first:
                canvas.SetLeftMargin(canvas.GetRightMargin()*1.1)

            canvas.SaveAs("%s/gifplots_%s_%s/rotscanbeta_%s_%i.png"%(opt.output,sig,dist,sig,theta))
            canvas.Clear()

            # save images to proper arrays
            imgAlpha=Image.open("%s/gifplots_%s_%s/rotscanalpha_%s_%i.png"%(opt.output,sig,dist,sig,theta))
            rotScanAlphaImgs+=[imgAlpha]
            imgBeta=Image.open("%s/gifplots_%s_%s/rotscanbeta_%s_%i.png"%(opt.output,sig,dist,sig,theta))
            rotScanBetaImgs+=[imgBeta]

        ##########################################
        # create 2D plots that scan in variables #
        ##########################################
        canvas.SetLogx(False)
        canvas.SetLogy(False)
        canvas.SetLogz(False)

        CMS_lumi.cmsTextOffset=0.1
        if first:
            canvas.SetRightMargin(canvas.GetRightMargin()*2)
            canvas.SetLeftMargin(canvas.GetLeftMargin()*2)

        for step in xrange(0,n2DScan) :
            alphaStep=alphaVar.getMin()+(alphaVar.getMax()-alphaVar.getMin())/n2DScan*step
            betaStep = betaVar.getMin()+( betaVar.getMax()- betaVar.getMin())/n2DScan*step

            alphaVar.setVal(alphaStep);
            betaVar.setVal( betaStep);

            # book histos
            histAlpha = mlbVar.createHistogram("Morphing against mass variations %i"%step,alphaVar)
            histBeta  = mlbVar.createHistogram("Morphing against width variations %i"%step,betaVar)
            sensHistAlpha = ROOT.TH2D("sensAlpha %i"%step,"Sensitivity against mass variations",
                    30,0,300,
                    n2DScan, alphaVar.getMin(), alphaVar.getMax())
            sensHistBeta  = ROOT.TH2D("sensBeta %i"%step,"Sensitivity against width variations",
                    30,0,300,
                    n2DScan, betaVar.getMin(), betaVar.getMax())

            morphPDF.fillHistogram(histAlpha,ROOT.RooArgList(mlbVar,alphaVar))
            morphPDF.fillHistogram(histBeta ,ROOT.RooArgList(mlbVar,betaVar))

            # mlb histo against mass
            histAlpha.SetTitle("")
            histAlpha.GetXaxis().SetTitle("%s [GeV]"%distTitle)
            histAlpha.GetYaxis().SetTitle("Grid width index")
            histAlpha.GetZaxis().SetRangeUser(0,zLimList["mlb"])
            histAlpha.Draw("COLZ")
            status.DrawLatexNDC(0.25,0.02,"m_{t}=%3.2f GeV"%(betaVar.getVal()*(maxMT-minMT)/betaVar.getMax()+minMT))

            CMS_lumi.CMS_lumi(canvas,4,0)
            canvas.SaveAs("%s/gifplots_%s_%s/betascan_%s_%i.png"%(opt.output,sig,dist,sig,step))
            canvas.Clear()

            # mlb histo against width
            histBeta.SetTitle("")
            histBeta.GetYaxis().SetTitle("Grid mass index")
            histBeta.GetXaxis().SetTitle("%s [GeV]"%distTitle)
            histBeta.GetZaxis().SetRangeUser(0,zLimList["mlb"])
            histBeta.Draw("COLZ")
            status.DrawLatexNDC(0.25,0.02,"#Gamma_{t}=%3.2f GeV"%(alphaVar.getVal()*(maxGammaT-minGammaT)/alphaVar.getMax()+minGammaT))

            CMS_lumi.CMS_lumi(canvas,4,0)
            canvas.SaveAs("%s/gifplots_%s_%s/alphascan_%s_%i.png"%(opt.output,sig,dist,sig,step))
            canvas.Clear()


            #####################################
            # create 2D local sensitivity scans #
            #####################################
            for ia,ib,ix in [(ia,ib,ix) for ia in range(1,n2DScan+1)
                    for ib in range(1,n2DScan+1)
                    for ix in range(1,31)] :
                if not opt.makeSens : break

                # get all the bin numbers
                gifBinA=sensHistAlpha.FindBin(ix*3-1.5,alphaStep)
                gifBinB=sensHistAlpha.FindBin(ix*3-1.5, betaStep)
                binNumA=sensHistAlpha.GetBin(ix,ia)
                binNumB= sensHistBeta.GetBin(ix,ib)

                # prepare alpha sensitivity plot
                alphaVar.setVal(sensHistAlpha.GetXaxis().GetBinCenter(binNumA));
                betaVar.setVal(  sensHistBeta.GetXaxis().GetBinCenter(gifBinB));
                mlbVar.setVal(  sensHistAlpha.GetYaxis().GetBinCenter(binNumA));
                f=pdf.getVal()
                if f!=0 :
                    dfdx=pdf.derivative(ws.var('x')).getVal()
                    sensHistAlpha.Fill(binNumA,(1/f)*(dfdx**2))

                # prepare beta sensitivity plots
                alphaVar.setVal(sensHistAlpha.GetXaxis().GetBinCenter(gifBinA));
                betaVar.setVal(  sensHistBeta.GetXaxis().GetBinCenter(binNumB));
                mlbVar.setVal(   sensHistBeta.GetYaxis().GetBinCenter(binNumB));
                f=pdf.getVal()
                if f!=0 :
                    dfdx=pdf.derivative(ws.var('x')).getVal()
                    sensHistBeta.Fill(binNumB,(1/f)*(dfdx**2))

            if opt.makeSens :
                ###################################
                # sensitivity of mlb against mass #
                ###################################
                if step == 0 : zLimList["asens"]=sensHistAlpha.GetMaximum()*2
                sensHistAlpha.SetTitle("")
                sensHistAlpha.GetXaxis().SetTitle("%s [GeV]"%distTitle)
                sensHistAlpha.GetYaxis().SetTitle("Generator-level width [GeV]")
                sensHistAlpha.GetZaxis().SetRangeUser(0,zLimList["asens"])
                sensHistAlpha.Draw("COLZ")
                status.DrawLatexNDC(0.25,0.02,"m_{t}=%3.2f GeV"%(betaStep))

                print sensHistAlpha.GetMaximum()

                CMS_lumi.CMS_lumi(canvas,4,0)
                canvas.SaveAs("%s/gifplots_%s_%s/sensbetascan_%s_%i.png"%(opt.output,sig,dist,sig,step))
                canvas.Clear()

                ####################################
                # sensitivity of mlb against width #
                ####################################
                if step == 0 : zLimList["bsens"]=sensHistBeta.GetMaximum()*2
                sensHistBeta.SetTitle("")
                sensHistBeta.GetXaxis().SetTitle("%s [GeV]"%distTitle)
                sensHistBeta.GetYaxis().SetTitle("Generator-level mass [GeV]")
                sensHistBeta.GetZaxis().SetRangeUser(0,zLimList["bsens"])
                sensHistBeta.Draw("COLZ")
                status.DrawLatexNDC(0.25,0.02,"#Gamma_{t}=%3.2f GeV"%(alphaStep))

                CMS_lumi.CMS_lumi(canvas,4,0)
                canvas.SaveAs("%s/gifplots_%s_%s/sensalphascan_%s_%i.png"%(opt.output,sig,dist,sig,step))
                canvas.Clear()

                # save images
                sensImgAlpha=Image.open("%s/gifplots_%s_%s/sensalphascan_%s_%i.png"%(opt.output,sig,dist,sig,step))
                sensAlphaScanImgs+=[sensImgAlpha]
                sensImgBeta=Image.open("%s/gifplots_%s_%s/sensbetascan_%s_%i.png"%(opt.output,sig,dist,sig,step))
                sensBetaScanImgs+=[sensImgBeta]


            # save images
            imgAlpha=Image.open("%s/gifplots_%s_%s/alphascan_%s_%i.png"%(opt.output,sig,dist,sig,step))
            alphaScanImgs+=[imgAlpha]
            imgBeta=Image.open("%s/gifplots_%s_%s/betascan_%s_%i.png"%(opt.output,sig,dist,sig,step))
            betaScanImgs+=[imgBeta]


        # make gif files from arrays
        writeGif("%s/gifplots_%s_%s/alphascan_%s.gif"%(opt.output,sig,dist,sig),alphaScanImgs,duration=.05)
        writeGif("%s/gifplots_%s_%s/betascan_%s.gif"%( opt.output,sig,dist,sig), betaScanImgs,duration=.05)
        writeGif("%s/gifplots_%s_%s/rotscanalpha_%s.gif"%(opt.output,sig,dist,sig),rotScanAlphaImgs,duration=.1)
        writeGif("%s/gifplots_%s_%s/rotscanbeta_%s.gif"%( opt.output,sig,dist,sig), rotScanBetaImgs,duration=.1)

        if opt.makeSens :
            writeGif("%s/gifplots_%s_%s/sensalphascan_%s.gif"%(opt.output,sig,dist,sig),sensAlphaScanImgs,duration=.05)
            writeGif("%s/gifplots_%s_%s/sensbetascan_%s.gif"%(opt.output,sig,dist,sig),sensBetaScanImgs,duration=.05)

        first=False

    print "\n Morphed dists created, workspace saved. Producing datacards: \n"

    ####################################
    # PRODUCE WIDTH/MASS SCAN DATACARD #
    ####################################
    fIn=ROOT.TFile.Open(opt.input)
    for lbCat,ch,cat,dist in [(lbCat,ch,cat,dist) for lbCat in lbCatList
            for ch in lfsList
            for cat in catList
            for dist in distList] :
        # get signal/backgrounds
        obs,exp=getMergedDists(fIn,('%s%s%s_%s_'%(lbCat,ch,cat,dist)),None,'',widList,nomWid,signalList)
        if not opt.truthDataset=="" :
            obs=makeMCTruthHist(opt.truthDataset,signalList,exp)

        # prepare datacard
        datacard=open('%s/datacard_widfit__%s%s%s_%s.dat'%(opt.output,lbCat,ch,cat,dist),'w')

        datacard.write('#\n')
        datacard.write('# Generated by %s with git hash %s for analysis category %s%s\n' % (getpass.getuser(),
            commands.getstatusoutput('git log --pretty=format:\'%h\' -n 1')[1],
            cat, ch) )
        datacard.write('#\n')

        # header
        datacard.write('imax *\n')
        datacard.write('jmax *\n')
        datacard.write('kmax *\n')

        # shapes locations
        datacard.write('-'*50+'\n')
        for proc in exp:
            isSig=False
            for sig in modWidList :
                if sig in proc : isSig=True
            if isSig : continue
            datacard.write('shapes %10s * shapes.root %s%s%s_%s/$PROCESS %s%s%s_%s_$SYSTEMATIC/$PROCESS\n'%(proc,lbCat,ch,cat,dist,lbCat,ch,cat,dist))

        datacard.write('shapes data_obs   * shapes.root %s%s%s_%s/$PROCESS\n'%(lbCat,ch,cat,dist,lbCat,ch,cat,dist))

        for sig in signalList:
            datacard.write('shapes %10s * shapes.root sigws_%s%s%s_$PROCESS_%s:widmorphpdf\n'%(sig,lbCat,ch,cat,dist))
        datacard.write('-'*50+'\n')

        # bin names
        datacard.write('bin 1\n')
        datacard.write('observation %3.1f\n' % obs.Integral())

        # observations
        datacard.write('-'*50+'\n')
        datacard.write('\t\t\t %32s'%'bin')
        for i in xrange(0,len(exp)-(len(widths)-1)*len(signalList)): datacard.write('%15s'%'1')
        datacard.write('\n')
        datacard.write('\t\t\t %32s'%'process')
        for sig in signalList:
            datacard.write('%15s'%(sig))
        for proc in exp:
            isSig=False
            for sig in modWidList :
                if sig in proc : isSig=True
            if isSig : continue
            datacard.write('%15s'%proc)
        datacard.write('\n')
        datacard.write('\t\t\t %32s'%'process')
        for i in xrange(0,len(signalList)) : datacard.write('%15s'%str(-1*(len(signalList)-1-i)))
        i=0
        for proc in exp:
            isSig=False
            for sig in modWidList :
                if sig in proc : isSig=True
            if isSig : continue
            i=i+1
            datacard.write('%15s'%str(i))
        datacard.write('\n')
        datacard.write('\t\t\t %32s'%'rate')
        for sig in signalList :
            datacard.write('%15s'%('%3.2f'%(exp['%s%s'%(sig,modNomWid)].Integral())))
        for proc in exp:
            isSig=False
            for sig in modWidList :
                if sig in proc : isSig=True
            if isSig : continue
            datacard.write('%15s'%('%3.2f'%exp[proc].Integral()))
        datacard.write('\n')
        datacard.write('-'*50+'\n')


        # rate uncertainties
        for syst,val,pdf,whiteList,blackList in rateSysts:

            datacard.write('%32s %8s'%(syst,pdf))
            entryTxt=''
            try:
                entryTxt='%15s'%('%3.3f/%3.3f'%(ROOT.TMath.Max(val[0],0.01),val[1]))
            except:
                entryTxt='%15s'%('%3.3f'%val)

            for sig in signalList:
                newSig='%s1p0w'%(sig)
                if (len(whiteList)==0 and not newSig in blackList) or newSig in whiteList:
                    datacard.write(entryTxt)
                else:
                    datacard.write('%15s'%'-')
            for proc in exp:
                isSig=False
                for sig in modWidList :
                    if sig in proc : isSig=True
                if isSig : continue
                if (len(whiteList)==0 and not proc in blackList) or proc in whiteList:
                    datacard.write(entryTxt)
                else:
                    datacard.write('%15s'%'-')
            datacard.write('\n')


        # write sample systematics to datacard
        for systVar, procsToApply, normalize, useAltShape, projectRelToNom in sampleSysts:
            datacard.write('%26s shape'%systVar)
            for sigproc in signalList:
                if ("%s1p0w"%(sigproc)) in procsToApply and ("%s1p0w"%(sigproc)) in upShapes[systVar]:
                    datacard.write('%15s'%'1')
                else:
                    datacard.write('%15s'%'-')
            for proc in exp:
                isSig=False
                for modwid in modWidList :
                    if modwid in proc : isSig=True
                if isSig : continue
                if proc in procsToApply and proc in upShapes[systVar]:
                    datacard.write('%15s'%'1')
                else:
                    datacard.write('%15s'%'-')
            datacard.write('\n')


        # write gen-level systematics to datacard
        for systVar, normalize, useAltShape, projectRelToNom in genSysts:
            datacard.write('%26s shape'%systVar)
            for sigproc in signalList:
                if ("%s1p0w"%(sigproc)) in upShapes[systVar]:
                    datacard.write('%15s'%'1')
                else:
                    datacard.write('%15s'%'-')
            for proc in exp:
                isSig=False
                for modwid in modWidList :
                    if modwid in proc : isSig=True
                if isSig : continue
                if proc in exp and proc in upShapes[systVar]:
                    datacard.write('%15s'%'1')
                else:
                    datacard.write('%15s'%'-')
            datacard.write('\n')

        datacard.close()


"""
for execution from another script
"""
if __name__ == "__main__":
    sys.exit(main())