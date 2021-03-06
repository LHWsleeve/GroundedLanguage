# Recurrent neural network which predicts Source, Target, and Relative Position independenantly
# Input File: JSONReader/data/2016-NAACL/SRD/*.mat

using ArgParse
using JLD
using CUDArt
device(0)
using Knet: stack_isempty
using Knet

function main(args)
    s = ArgParseSettings()
    s.exc_handler=ArgParse.debug_handler
    @add_arg_table s begin
        ("--datafiles"; nargs='+'; default=["JSONReader/data/2016-NAACL/SRD/Train.mat",
                                            "JSONReader/data/2016-NAACL/SRD/Dev.mat",
                                            "JSONReader/data/2016-NAACL/SRD/Test.mat"])
        ("--loadfile"; help="initialize model from file")
        ("--savefile"; help="save final model to file")
        ("--bestfile"; help="save best model to file")
        ("--hidden"; arg_type=Int; default=256; help="hidden layer size") # DY: best 64 for 1, 128 for 2, 256 for 3.
        ("--embedding"; arg_type=Int; default=0; help="word embedding size (default same as hidden)")
        ("--epochs"; arg_type=Int; default=40; help="number of epochs to train")
        ("--batchsize"; arg_type=Int; default=10; help="minibatch size")
        ("--lr"; arg_type=Float64; default=1.0; help="learning rate")
        ("--gclip"; arg_type=Float64; default=5.0; help="gradient clipping threshold")
        ("--dropout"; arg_type=Float64; default=0.5; help="dropout probability")
        ("--decay"; arg_type=Float64; default=0.9; help="learning rate decay if deverr increases")
        ("--nogpu"; action = :store_true; help="do not use gpu, which is used by default if available")
        ("--seed"; arg_type=Int; default=20160427; help="random number seed")
        ("--target"; arg_type=Int; default=1; help="which target to predict: 1:source,2:target,3:direction")
        # DY: this is read from the data now
        # ("--yvocab"; arg_type=Int; nargs='+'; default=[20,20,9]; help="vocab sizes for target columns (all columns assumed independent)")
        ("--xsparse"; action = :store_true; help="use sparse inputs, dense arrays used by default")
        ("--ftype"; default = "Float32"; help="floating point type to use: Float32 or Float64")
    end
    isa(args, AbstractString) && (args=split(args))
    o = parse_args(args, s; as_symbols=true); println(o)
    o[:seed] > 0 && setseed(o[:seed])
    o[:ftype] = eval(parse(o[:ftype]))
    o[:embedding] == 0 && (o[:embedding] = o[:hidden])
    Knet.gpu(!o[:nogpu])

    # Read data files:
    global rawdata = map(f->readdlm(f), o[:datafiles])
    global yrange = 1:3
    global yvocabs = zeros(yrange)
    # global yvocab = o[:yvocab][o[:target]] # DY: We should get this from the data as well like xvocab?
    global xvocab = 0
    global xranges = cell(length(rawdata))

    for i=1:length(rawdata)
        rawdata[i][rawdata[i].==""]=0 # DY: use word=0 for padding, word=1 for unk.
        if size(rawdata[i],2) < 82
          rawdata[i] = hcat(rawdata[i], zeros(Int,size(rawdata[i],1),82-size(rawdata[i],2)))
        end

        rawdata[i] = convert(Array{Int,2},rawdata[i]);
        rawdata[i][:,yrange] += 1   # DY: converting from 0-based to 1-based, better to fix the data and remove this hack.
        xranges[i] = (1+maximum(yrange)):size(rawdata[i],2)
        xvocab = max(xvocab, maximum(rawdata[i][:,xranges[i]]))
        for j in 1:length(yvocabs)
            yvocabs[j] = max(yvocabs[j], maximum(rawdata[i][:,yrange[j]]))
        end
    end

    global trange = yrange[o[:target]]      # DY: we want to use only one of the y values as output.
    trange = trange:trange                  # DY: minibatch expects ranges for both x and y, so use a singleton range for y
    global tvocab = yvocabs[o[:target]]

    global data = cell(length(rawdata))
    for i=1:length(rawdata)
        data[i] = minibatch(rawdata[i], xranges[i], trange, o[:batchsize]; xvocab=xvocab, yvocab=tvocab, ftype=o[:ftype], xsparse=o[:xsparse])
    end

    # Load or create the model:
    global net = (o[:loadfile]!=nothing ? load(o[:loadfile], "net") :
                  compile(:rnnmodel; hidden=o[:hidden], embedding=o[:embedding], output=tvocab, pdrop=o[:dropout]))
    if o[:loadfile] != nothing
      println(predict(net, rawdata[3]; xvocab=xvocab, ftype=o[:ftype], xsparse=o[:xsparse]))
    else
      setp(net, lr=o[:lr])
      lasterr = besterr = 1.0
      for epoch=1:o[:epochs]      # TODO: experiment with pretraining
          trnloss = train(net, data[1], softloss; gclip=o[:gclip])
          deverr = test(net, data[2], zeroone)
          tsterr = test(net, data[3], zeroone)
          println((epoch, o[:lr], trnloss, deverr, tsterr)); flush(STDOUT)
          if deverr < besterr
              besterr=deverr
              o[:bestfile]!=nothing && save(o[:bestfile], "net", clean(net))
          end
          if deverr > lasterr
              o[:lr] *= o[:decay]
              setp(net, lr=o[:lr])
          end
          lasterr = deverr
      end
      o[:savefile]!=nothing && save(o[:savefile], "net", clean(net))
      @date devpred = predict(net, rawdata[2]; xvocab=xvocab, ftype=o[:ftype], xsparse=o[:xsparse])
      println(devpred)
    end
end

@knet function rnnmodel(word; hidden=100, embedding=hidden, output=20, pdrop=0.5)
    wvec = wdot(word; out=embedding)                 # TODO: try different embedding dimension than hidden
    hvec = lstm(wvec; out=hidden)                    # TODO: try more layers
    if predict                                       # TODO: try dropout between wdot and lstm
        dvec = drop(hvec; pdrop=pdrop)
        return wbf(dvec; out=output, f=:soft)
    end
end

### Minibatched data format:
# data is an array of (x,y,mask) triples
# x[xvocab+1,batchsize] contains one-hot word columns for the n'th word of batchsize sentences
# xvocab+1=eos is used for end-of-sentence
# sentences in a batch are padded at the beginning and get an eos at the end
# mask[batchsize] indicates whether i'th column of x is padding or not
# y is nothing until the very last token of a sentence batch
# y[yvocab,batchsize] contains one-hot target columns with the last token (eos) of a sentence batch

function train(f, data, loss; gclip=0)
    sumloss = numloss = 0
    reset!(f)
    for (x,y,mask) in data
        ypred = sforw(f, x, predict=(y!=nothing), dropout=true)
        y==nothing && continue
        sumloss += zeroone(ypred, y)*size(y,2)
        numloss += size(y,2)
        sback(f, y, loss; mask=mask)
        while !stack_isempty(f); sback(f); end
        update!(f; gclip=gclip)
        reset!(f)
    end
    sumloss / numloss
end

function test(f, data, loss)
    sumloss = numloss = 0
    reset!(f)
    for (x,y,mask) in data
        ypred = forw(f, x, predict=(y!=nothing))
        y==nothing && continue
        sumloss += loss(ypred, y)*size(y,2)
        numloss += size(y,2)
        reset!(f)
    end
    sumloss / numloss
end

function predict(f, data; xrange=4:82, padding=0, xvocab=326, ftype=Float32, xsparse=false)
    reset!(f)
    sentences = extract(data, xrange; padding=padding)	# sentences[i][j] = j'th word of i'th sentence
    ypred = Any[]
    eos = xvocab + 1
    x = (xsparse ? sponehot : zeros)(ftype, eos, 1)
    for s in sentences
        for i = 1:length(s)
            setrow!(x, s[i], 1)
            forw(f, x, predict=false)
        end
        setrow!(x, eos, 1)
        y = forw(f, x, predict=true)
        push!(ypred, indmax(to_host(y)))
        reset!(f)
    end
    println(ypred)
end

# DY: minibatch called with (d is rawdata, with each row an instance)
# minibatch(d, xrange, yrange, o[:batchsize]; xvocab=xvocab, yvocab=yvocab, ftype=o[:ftype], xsparse=o[:xsparse])

function minibatch(data, xrange, yrange, batchsize; o...) # data[i,j] is the j'th entry of i'th instance
    x = extract(data, xrange; padding=0)	# x[i][j] = j'th word of i'th sentence
    y = extract(data, yrange)                   # y[i][j] = j'th class of i'th sentence, here we assume j=1, i.e. single output for each sentence
    s = sortperm(x, by=length)
    batches = Any[]
    for i=1:batchsize:length(x)
        j=min(i+batchsize-1,length(x))
        xx,yy = x[s[i:j]],y[s[i:j]]
        batchsentences(xx, yy, batches; o...)
    end
    return batches
end

function extract(data, xrange; padding=nothing)
    inst = Any[]
    for i=1:size(data,1)
        s = vec(data[i,xrange])
        if padding != nothing
            while s[end]==padding; pop!(s); end
        end
        push!(inst,s)
    end
    return inst
end

function batchsentences(x, y, batches; xvocab=326, yvocab=20, ftype=Float32, xsparse=false)
    @assert maximum(map(maximum,x)) <= xvocab
    @assert maximum(map(maximum,y)) <= yvocab
    eos = xvocab + 1
    batchsize = length(x)                       # number of sentences in batch
    maxlen = maximum(map(length,x))
    for t=1:maxlen+1                            # pad sentences in the beginning and add eos at the end
        xbatch = (xsparse ? sponehot : zeros)(ftype, eos, batchsize)
        mask = zeros(Cuchar, batchsize)         # mask[i]=0 if xbatch[:,i] is padding
        for s=1:batchsize                       # set xbatch[word][s]=1 if x[s][t]=word
            sentence = x[s]
            position = t - maxlen + length(sentence)
            if position < 1
                mask[s] = 0
            elseif position <= length(sentence)
                word = sentence[position]
                setrow!(xbatch, word, s)
                mask[s] = 1
            elseif position == 1+length(sentence)
                word = eos
                setrow!(xbatch, word, s)
                mask[s] = 1
            else
                error("This should not be happening")
            end
        end
        if t <= maxlen
            ybatch = nothing
        else
            ybatch = zeros(ftype, yvocab, batchsize)
            for s=1:batchsize
                answer = y[s][1]
                setrow!(ybatch, answer, s)
            end
        end
        push!(batches, (xbatch, ybatch, mask))
    end
end

# These assume one hot columns:
# setrow!(x::SparseMatrixCSC,i,j)=(i>0 ? (x.rowval[j] = i; x.nzval[j] = 1) : (x.rowval[j]=1; x.nzval[j]=0); x)
# setrow!(x::Array,i,j)=(x[:,j]=0; i>0 && (x[i,j]=1); x)

# DY: It should be an error to try to set 0
setrow!(x::SparseMatrixCSC,i,j)=(i>0 ? (x.rowval[j] = i; x.nzval[j] = 1) : error("setting row 0"); x)
setrow!(x::Array,i,j)=(x[:,j]=0; i>0 ? x[i,j]=1 : error("setting row 0"); x)

#!isinteractive() && main(ARGS)
main(ARGS)
