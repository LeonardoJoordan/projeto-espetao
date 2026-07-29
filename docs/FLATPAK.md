# Flatpak do PDV Espetinho

O manifesto `com.leobelisario.Espetao.yaml` segue o mesmo modelo simples do
ProjetoComSoc: dependências Python em um módulo e arquivos do aplicativo em
outro.

## Construir

```bash
flatpak-builder --force-clean build-flatpak com.leobelisario.Espetao.yaml
```

## Instalar para teste

```bash
flatpak-builder --user --install --force-clean build-flatpak com.leobelisario.Espetao.yaml
flatpak run com.leobelisario.Espetao
```

## Gerar um arquivo instalável

```bash
flatpak-builder --repo=repo-flatpak --force-clean build-flatpak com.leobelisario.Espetao.yaml
flatpak build-bundle repo-flatpak Espetao.flatpak com.leobelisario.Espetao
```

## Dados e funcionamento offline

- O banco, as fotos cadastradas e a configuração da impressora ficam na área
  persistente privada do aplicativo, em `~/.var/app/com.leobelisario.Espetao`.
- O aplicativo não usa CDN nem baixa recursos durante a execução.
- A permissão de rede em execução é necessária para o servidor local ser
  acessado pelos celulares e para a impressora térmica por IP.
- A internet é necessária apenas na construção do pacote, para o `pip` baixar
  as dependências. O arquivo `.flatpak` pronto pode ser instalado e usado
  offline.
