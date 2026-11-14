$ErrorActionPreference = 'Stop'

while ($true) {
    $line = [Console]::In.ReadLine()
    if ($null -eq $line) { break }

    $client = $null
    $stream = $null
    try {
        $parts = $line.Split('|')
        if ($parts.Length -ne 6) { throw 'Expected targetHost|connectHost|port|requestPath|replyLength|writeChunks' }
        $targetHost = $parts[0]
        $connectHost = $parts[1]
        $port = [int]$parts[2]
        $requestPath = $parts[3]
        $replyLength = [int]$parts[4]
        $writeChunkField = $parts[5]

        $client = [System.Net.Sockets.TcpClient]::new()
        $client.Connect($connectHost, $port)
        $acceptCertificate = [System.Net.Security.RemoteCertificateValidationCallback] {
            param($sender, $certificate, $chain, $errors)
            return $true
        }
        $stream = [System.Net.Security.SslStream]::new(
            $client.GetStream(), $false, $acceptCertificate
        )
        $stream.AuthenticateAsClient(
            $targetHost,
            $null,
            [System.Security.Authentication.SslProtocols]::Tls12,
            $false
        )

        $request = [System.IO.File]::ReadAllBytes($requestPath)
        if ($writeChunkField -eq '-') {
            $stream.Write($request, 0, $request.Length)
        }
        else {
            $offset = 0
            foreach ($chunkText in $writeChunkField.Split(',')) {
                $chunkSize = [int]$chunkText
                $stream.Write($request, $offset, $chunkSize)
                $offset += $chunkSize
            }
            if ($offset -ne $request.Length) { throw 'Write chunks do not sum to request length' }
        }
        $stream.Flush()

        $reply = New-Object byte[] $replyLength
        $offset = 0
        while ($offset -lt $replyLength) {
            $count = $stream.Read($reply, $offset, $replyLength - $offset)
            if ($count -le 0) {
                throw "TLS peer closed after $offset of $replyLength reply bytes"
            }
            $offset += $count
        }
        [Console]::Out.WriteLine('OK')
        [Console]::Out.Flush()
    }
    catch {
        [Console]::Error.WriteLine($_.ToString())
        [Console]::Out.WriteLine('ERR')
        [Console]::Out.Flush()
    }
    finally {
        if ($null -ne $stream) { $stream.Dispose() }
        if ($null -ne $client) { $client.Dispose() }
    }
}
